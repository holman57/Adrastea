import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from ..config import config
from .gemini_governor import GeminiUsageGovernor, gemini_governor

logger = logging.getLogger("Adrastea.Beta.LLM")


class LLMConsultant:
    """Consults external frontier models (Google Gemini) or local LLMs (via Ollama/MCP)
    based on task complexity, operator preferences, and strict quota governor constraints.
    """

    def __init__(self, governor: Optional[GeminiUsageGovernor] = None):
        self.gemini_key = config.gemini_api_key
        self.gemini_model = config.gemini_model
        self.ollama_url = config.ollama_base_url
        self.ollama_model = config.ollama_model
        self.governor = governor or gemini_governor

    def consult(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        preferred_provider: str = "balanced",
    ) -> str:
        """Query LLM with intelligent quota-aware provider routing:
        - "local_mcp" / "local": Prioritizes local Ollama inference; zero external token consumption.
        - "balanced" / "auto": Uses local Ollama for routine queries or when Gemini quota is constrained;
                               uses Gemini for high-level reasoning when budget allows.
        - "gemini": Prefers Gemini, but strictly respects Governor RPM/RPH/daily budgets and circuit breaker,
                    falling back cleanly to local Ollama on throttle or error.
        """
        # 1. Check in-memory LRU prompt cache (Zero cost, instantaneous)
        cached_resp = self.governor.get_cached_response(prompt, system_prompt)
        if cached_resp:
            return cached_resp

        # 2. Local-First routing
        routing_mode = getattr(config, "gemini_routing_mode", "balanced").lower()
        if preferred_provider in ("local_mcp", "local") or routing_mode == "local_first":
            local_resp = self._query_ollama(prompt, system_prompt)
            if local_resp and not local_resp.startswith("Adrastea reasoning fallback"):
                self.governor.put_cached_response(prompt, system_prompt, local_resp)
                return local_resp
            logger.info("Local LLM unavailable or failed; checking if Gemini is eligible as fallback...")

        # 3. Check Gemini Quota & Rate Limit Governor
        can_call, throttle_reason = self.governor.can_call_gemini()
        if can_call and self.gemini_key:
            try:
                gemini_resp = self._query_gemini(prompt, system_prompt)
                if gemini_resp:
                    self.governor.record_gemini_call(prompt, gemini_resp)
                    self.governor.put_cached_response(prompt, system_prompt, gemini_resp)
                    return gemini_resp
            except urllib.error.HTTPError as e:
                if e.code == 429 or "quota" in str(e).lower():
                    self.governor.trip_circuit_breaker(f"HTTP Error {e.code}: Rate limit / Quota exceeded")
                else:
                    logger.warning(f"Gemini consultation HTTP error {e.code}: {e.reason}")
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str or "rate" in err_str:
                    self.governor.trip_circuit_breaker(f"Rate limit exceeded: {e}")
                else:
                    logger.warning(f"Gemini consultation failed: {e}")
        else:
            logger.info(
                f"Gemini consultation skipped: {throttle_reason}. "
                f"Routing seamlessly to local Ollama ({self.ollama_model}) to preserve quota."
            )

        # 4. Fallback to local Ollama
        local_result = self._query_ollama(prompt, system_prompt)
        if local_result and not local_result.startswith("Adrastea reasoning fallback"):
            self.governor.put_cached_response(prompt, system_prompt, local_result)
        return local_result

    def _query_gemini(self, prompt: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """Direct REST call to Google Gemini Generative Language API."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Directive: {system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow your directive."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        body = json.dumps({"contents": contents}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()
        return None

    def _query_ollama(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call local Ollama instance (e.g. qwen3-coder:30b)."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.3}
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=45) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception as e:
            logger.debug(f"Local Ollama query failed: {e}")
            return f"Adrastea reasoning fallback: Unable to consult LLM ({e})"
