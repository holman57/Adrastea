import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..alpha.local_llm import LocalLLMClient
from ..config import config

logger = logging.getLogger("Adrastea.Beta.DeliveryStrategist")


class DeliveryStrategist:
    """Beta cognitive strategist for diagnosing delivery barriers and adapting contact channels.
    
    Uses the local Ollama LLM exclusively to conserve Gemini token allocation.
    """

    def __init__(self, local_llm: Optional[LocalLLMClient] = None, state_file: Optional[Path] = None, persist_state: bool = True):
        self.local_llm = local_llm or LocalLLMClient()
        self.state_file = state_file or (config.data_dir / "delivery_state.json")
        self.persist_state = persist_state
        self.contact_attempt_count = 0
        self.last_contact_time = 0.0
        self.is_waiting_for_response = False
        # Adaptive backoff schedule in minutes: 15m, 30m, 60m, 120m, 240m
        self.backoff_intervals = [15 * 60, 30 * 60, 60 * 60, 120 * 60, 240 * 60]
        if self.persist_state:
            self._load_state()

    def _load_state(self) -> None:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.contact_attempt_count = data.get("contact_attempt_count", 0)
                    self.last_contact_time = data.get("last_contact_time", 0.0)
                    self.is_waiting_for_response = data.get("is_waiting_for_response", False)
            except Exception as e:
                logger.debug(f"Failed to load delivery state: {e}")

    def _save_state(self) -> None:
        if not self.persist_state:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "contact_attempt_count": self.contact_attempt_count,
                    "last_contact_time": self.last_contact_time,
                    "is_waiting_for_response": self.is_waiting_for_response,
                }, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save delivery state: {e}")

    def get_next_wait_interval(self) -> float:
        """Returns the wait interval for backoff if user hasn't responded."""
        idx = min(self.contact_attempt_count, len(self.backoff_intervals) - 1)
        return self.backoff_intervals[idx]

    def should_attempt_contact(self) -> bool:
        """Checks if contact should be attempted.
        Strictly enforces wait-for-response:
        When Adrastea has already contacted or asked Luke, it enters waiting mode
        and will NOT ask again until Luke responds.
        """
        if self.is_waiting_for_response or self.contact_attempt_count > 0:
            return False
        return True

    def mark_contact_attempted(self) -> None:
        self.contact_attempt_count += 1
        self.last_contact_time = time.time()
        self.is_waiting_for_response = True
        self._save_state()
        logger.info(f"Marked contact attempt #{self.contact_attempt_count}. System in wait-for-response mode (will not ask again).")

    def reset_backoff_on_response(self) -> None:
        """Reset backoff counter and waiting state when Luke responds with a directive."""
        logger.info("User response detected! Resetting contact waiting state and backoff schedule.")
        self.contact_attempt_count = 0
        self.is_waiting_for_response = False
        self._save_state()

    def analyze_and_adapt(self, outreach_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Diagnose failed channels and recommend adaptations using local Ollama model."""
        failures = {k: v for k, v in outreach_results.items() if not v.get("success")}
        successes = {k: v for k, v in outreach_results.items() if v.get("success")}

        if not failures:
            return {
                "diagnosis": "All notification channels delivered successfully.",
                "action": "MAINTAIN",
                "recommended_channels": list(successes.keys())
            }

        logger.warning(f"Beta analyzing {len(failures)} outreach failures: {list(failures.keys())}")

        prompt = (
            f"Adrastea attempted to contact user via configured notification channels.\n"
            f"Results:\n"
            f"Successes: {list(successes.keys())}\n"
            f"Failures: {failures}\n\n"
            f"Formulate a brief strategic adaptation to ensure the user receives notifications.\n"
            f"Format as JSON with keys 'barrier_summary', 'best_working_channel', 'recommendation'.\n"
            f"JSON:"
        )

        resp = self.local_llm.generate(
            prompt,
            system="You are System Beta cognitive delivery optimizer. Return valid JSON only.",
            temperature=0.1
        )

        analysis = {}
        if resp:
            try:
                clean = resp.strip().strip("`")
                if clean.startswith("json"):
                    clean = clean[4:].strip()
                analysis = json.loads(clean)
            except Exception:
                pass

        if not analysis:
            analysis = {
                "barrier_summary": "Direct ISP / unauthenticated SMTP blocked by Google SPF/DKIM; GitHub relay and desktop channels operating.",
                "best_working_channel": "github_verified_email",
                "recommendation": "Prioritize GitHub verified email and desktop audio alerts."
            }

        return analysis
