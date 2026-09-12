import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..config import config

logger = logging.getLogger("Adrastea.Beta.GeminiGovernor")


class GeminiUsageGovernor:
    """Manages and throttles Google Gemini API consumption to prevent quota exhaustion,
    rate limit violations (HTTP 429), and excessive token usage.

    Features:
    1. Sliding-window rate limiting (Requests Per Minute & Requests Per Hour).
    2. Daily request budget enforcement with automatic UTC rollover.
    3. Automatic Circuit Breaker: Enters cooldown when HTTP 429 or quota errors occur.
    4. LRU Prompt Response Caching with TTL: Identical queries return cached results with 0 API calls.
    5. Persistent metrics tracking saved to data/gemini_usage.json.
    6. Seamless degradation: Redirects queries to local Ollama (qwen3-coder:30b) when Gemini is throttled.
    """

    def __init__(self, state_file: Optional[Path] = None, persist_state: bool = True):
        self.state_file = state_file or (config.data_dir / "gemini_usage.json")
        self.persist_state = persist_state
        self.cache: Dict[str, Dict[str, Any]] = {}

        # Usage State
        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.requests_today = 0
        self.current_date_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.requests_this_hour = 0
        self.current_hour_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")
        self.last_request_timestamp = 0.0
        self.recent_request_timestamps: list[float] = []

        # Circuit Breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_until = 0.0
        self.circuit_breaker_reason = ""

        if self.persist_state:
            self._load_state()

    def _load_state(self) -> None:
        """Loads usage statistics from disk."""
        if not self.state_file.exists():
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.total_requests = data.get("total_requests", 0)
            self.total_input_tokens = data.get("total_input_tokens", 0)
            self.total_output_tokens = data.get("total_output_tokens", 0)
            self.last_request_timestamp = data.get("last_request_timestamp", 0.0)

            saved_date = data.get("current_date_utc", "")
            now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if saved_date == now_date:
                self.requests_today = data.get("requests_today", 0)
            else:
                self.requests_today = 0
                self.current_date_utc = now_date

            saved_hour = data.get("current_hour_utc", "")
            now_hour = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:00")
            if saved_hour == now_hour:
                self.requests_this_hour = data.get("requests_this_hour", 0)
            else:
                self.requests_this_hour = 0
                self.current_hour_utc = now_hour

            self.circuit_breaker_active = data.get("circuit_breaker_active", False)
            self.circuit_breaker_until = data.get("circuit_breaker_until", 0.0)
            self.circuit_breaker_reason = data.get("circuit_breaker_reason", "")

            # Check if circuit breaker has expired
            if self.circuit_breaker_active and time.time() >= self.circuit_breaker_until:
                self.circuit_breaker_active = False
                self.circuit_breaker_until = 0.0
                self.circuit_breaker_reason = ""

        except Exception as e:
            logger.debug(f"Failed to load Gemini usage state: {e}")

    def _save_state(self) -> None:
        """Persists usage statistics to disk."""
        if not self.persist_state:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "total_requests": self.total_requests,
                    "total_input_tokens": self.total_input_tokens,
                    "total_output_tokens": self.total_output_tokens,
                    "requests_today": self.requests_today,
                    "current_date_utc": self.current_date_utc,
                    "requests_this_hour": self.requests_this_hour,
                    "current_hour_utc": self.current_hour_utc,
                    "last_request_timestamp": self.last_request_timestamp,
                    "circuit_breaker_active": self.circuit_breaker_active,
                    "circuit_breaker_until": self.circuit_breaker_until,
                    "circuit_breaker_reason": self.circuit_breaker_reason,
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save Gemini usage state: {e}")

    def _check_rollover(self) -> None:
        """Rolls over daily and hourly counters based on UTC time."""
        now_dt = datetime.now(timezone.utc)
        now_date = now_dt.strftime("%Y-%m-%d")
        now_hour = now_dt.strftime("%Y-%m-%d %H:00")

        if self.current_date_utc != now_date:
            logger.info(f"Gemini usage daily rollover: Resetting requests_today (was {self.requests_today}).")
            self.requests_today = 0
            self.current_date_utc = now_date

        if self.current_hour_utc != now_hour:
            self.requests_this_hour = 0
            self.current_hour_utc = now_hour

    def can_call_gemini(self) -> Tuple[bool, str]:
        """Validates all quota, budget, rate limit, and circuit breaker constraints.
        Returns (True, 'OK') if Gemini may be called, or (False, reason) if call should be throttled.
        """
        if not getattr(config, "gemini_enabled", True):
            return False, "Gemini is disabled in configuration."

        if not getattr(config, "gemini_api_key", None):
            return False, "Gemini API key is not configured."

        now = time.time()
        self._check_rollover()

        # 1. Check Circuit Breaker
        if self.circuit_breaker_active:
            if now < self.circuit_breaker_until:
                remaining_s = int(self.circuit_breaker_until - now)
                return False, f"Circuit breaker active ({self.circuit_breaker_reason}); cooling down for {remaining_s}s."
            else:
                self.circuit_breaker_active = False
                self.circuit_breaker_until = 0.0
                self.circuit_breaker_reason = ""
                logger.info("Gemini circuit breaker cooldown expired; resetting to operational state.")

        # 2. Check Minimum Interval (Pacing)
        min_interval = getattr(config, "gemini_min_interval_seconds", 10.0)
        elapsed = now - self.last_request_timestamp
        if self.last_request_timestamp > 0 and elapsed < min_interval:
            wait_needed = round(min_interval - elapsed, 1)
            return False, f"Pacing interval active ({elapsed:.1f}s < {min_interval}s; wait {wait_needed}s)."

        # 3. Check Requests Per Minute (Sliding window)
        max_rpm = getattr(config, "gemini_max_requests_per_minute", 4)
        one_min_ago = now - 60.0
        self.recent_request_timestamps = [t for t in self.recent_request_timestamps if t > one_min_ago]
        if len(self.recent_request_timestamps) >= max_rpm:
            return False, f"RPM limit reached ({len(self.recent_request_timestamps)}/{max_rpm} in last 60s)."

        # 4. Check Requests Per Hour
        max_rph = getattr(config, "gemini_max_requests_per_hour", 20)
        if self.requests_this_hour >= max_rph:
            return False, f"Hourly limit reached ({self.requests_this_hour}/{max_rph} this hour)."

        # 5. Check Daily Request Budget
        max_rpd = getattr(config, "gemini_max_requests_per_day", 60)
        if self.requests_today >= max_rpd:
            return False, f"Daily budget reached ({self.requests_today}/{max_rpd} today)."

        return True, "Quota verified and available."

    def record_gemini_call(self, prompt: str, response: str) -> None:
        """Records a completed Gemini API invocation and updates token and usage metrics."""
        now = time.time()
        self._check_rollover()

        self.last_request_timestamp = now
        self.recent_request_timestamps.append(now)
        self.requests_this_hour += 1
        self.requests_today += 1
        self.total_requests += 1

        # Token estimation: ~4 chars per token rule of thumb
        in_tokens = max(1, len(prompt) // 4)
        out_tokens = max(1, len(response) // 4)
        self.total_input_tokens += in_tokens
        self.total_output_tokens += out_tokens

        logger.info(
            f"Gemini call recorded (+{in_tokens} in, +{out_tokens} out tokens). "
            f"Usage today: {self.requests_today}/{getattr(config, 'gemini_max_requests_per_day', 60)} | "
            f"This hour: {self.requests_this_hour}/{getattr(config, 'gemini_max_requests_per_hour', 20)}"
        )
        self._save_state()

    def trip_circuit_breaker(self, reason: str, cooldown_seconds: Optional[float] = None) -> None:
        """Activates the circuit breaker upon encountering rate limits (HTTP 429) or quota errors.
        Prevents further Gemini requests for the duration of the cooldown.
        """
        cooldown = cooldown_seconds or getattr(config, "gemini_circuit_breaker_cooldown_seconds", 900.0)
        self.circuit_breaker_active = True
        self.circuit_breaker_until = time.time() + cooldown
        self.circuit_breaker_reason = reason
        cooldown_mins = round(cooldown / 60.0, 1)

        logger.warning(
            f"🚨 Gemini Circuit Breaker TRIPPED: {reason}. "
            f"Suspending Gemini calls for {cooldown_mins} minutes ({int(cooldown)}s). "
            f"All cognitive tasks will route to local Ollama (qwen3-coder:30b)."
        )
        self._save_state()

    def get_cache_key(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Computes deterministic SHA-256 hash of prompt and system prompt for caching."""
        combined = f"SYS:{system_prompt or ''}__USER:{prompt}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def get_cached_response(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Retrieves cached response if available and within TTL."""
        key = self.get_cache_key(prompt, system_prompt)
        entry = self.cache.get(key)
        if not entry:
            return None

        ttl = getattr(config, "gemini_cache_ttl_seconds", 7200.0)
        if time.time() - entry["timestamp"] > ttl:
            del self.cache[key]
            return None

        logger.debug(f"Gemini Cache Hit! Saved external API call for prompt hash {key[:10]}.")
        return entry["response"]

    def put_cached_response(self, prompt: str, system_prompt: Optional[str], response: str) -> None:
        """Stores a prompt-response pair in the in-memory cache."""
        key = self.get_cache_key(prompt, system_prompt)
        # Limit cache size to 100 entries
        if len(self.cache) >= 100:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]["timestamp"])
            del self.cache[oldest_key]

        self.cache[key] = {
            "response": response,
            "timestamp": time.time(),
        }

    def get_usage_summary(self) -> Dict[str, Any]:
        """Returns structured metrics for CLI, logs, and telemetry."""
        now = time.time()
        self._check_rollover()
        max_rpd = getattr(config, "gemini_max_requests_per_day", 60)
        max_rph = getattr(config, "gemini_max_requests_per_hour", 20)
        max_rpm = getattr(config, "gemini_max_requests_per_minute", 4)

        cooldown_rem = max(0, int(self.circuit_breaker_until - now)) if self.circuit_breaker_active else 0

        return {
            "gemini_enabled": getattr(config, "gemini_enabled", True),
            "model": getattr(config, "gemini_model", "gemini-2.5-flash"),
            "routing_mode": getattr(config, "gemini_routing_mode", "balanced"),
            "circuit_breaker": {
                "active": self.circuit_breaker_active and cooldown_rem > 0,
                "cooldown_remaining_seconds": cooldown_rem,
                "reason": self.circuit_breaker_reason if (self.circuit_breaker_active and cooldown_rem > 0) else None,
            },
            "requests": {
                "today": self.requests_today,
                "daily_budget": max_rpd,
                "daily_remaining": max(0, max_rpd - self.requests_today),
                "this_hour": self.requests_this_hour,
                "hourly_budget": max_rph,
                "hourly_remaining": max(0, max_rph - self.requests_this_hour),
                "max_rpm": max_rpm,
                "total_lifetime": self.total_requests,
            },
            "tokens": {
                "total_estimated_input": self.total_input_tokens,
                "total_estimated_output": self.total_output_tokens,
                "total_estimated": self.total_input_tokens + self.total_output_tokens,
            },
            "cache": {
                "cached_entries": len(self.cache),
            },
        }


# Global governor singleton
gemini_governor = GeminiUsageGovernor()
