import os
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from adrastea.beta.gemini_governor import GeminiUsageGovernor
from adrastea.beta.llm_consultant import LLMConsultant
from adrastea.config import config


class TestGeminiQuotaGovernor(unittest.TestCase):
    def setUp(self):
        self.test_state = Path("data/test_gemini_usage.json")
        if self.test_state.exists():
            self.test_state.unlink()
        self.governor = GeminiUsageGovernor(state_file=self.test_state, persist_state=True)

    def tearDown(self):
        if self.test_state.exists():
            self.test_state.unlink()

    def test_pacing_minimum_interval(self):
        """Governor enforces minimum seconds between calls."""
        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"), \
             patch.object(config, "gemini_min_interval_seconds", 5.0):

            allowed, reason = self.governor.can_call_gemini()
            self.assertTrue(allowed)

            # Record call
            self.governor.record_gemini_call("Hello", "World")

            # Immediate next check should be throttled by pacing
            allowed2, reason2 = self.governor.can_call_gemini()
            self.assertFalse(allowed2)
            self.assertIn("Pacing interval active", reason2)

    def test_rpm_sliding_window_limit(self):
        """Governor enforces Requests Per Minute sliding window."""
        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"), \
             patch.object(config, "gemini_min_interval_seconds", 0.0), \
             patch.object(config, "gemini_max_requests_per_minute", 2):

            # 2 allowed calls
            self.governor.record_gemini_call("P1", "R1")
            self.governor.record_gemini_call("P2", "R2")

            # 3rd call exceeds RPM
            allowed, reason = self.governor.can_call_gemini()
            self.assertFalse(allowed)
            self.assertIn("RPM limit reached", reason)

    def test_hourly_limit(self):
        """Governor enforces hourly request ceiling."""
        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"), \
             patch.object(config, "gemini_min_interval_seconds", 0.0), \
             patch.object(config, "gemini_max_requests_per_minute", 100), \
             patch.object(config, "gemini_max_requests_per_hour", 3):

            self.governor.requests_this_hour = 3
            allowed, reason = self.governor.can_call_gemini()
            self.assertFalse(allowed)
            self.assertIn("Hourly limit reached", reason)

    def test_daily_budget_limit(self):
        """Governor enforces daily budget cap."""
        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"), \
             patch.object(config, "gemini_min_interval_seconds", 0.0), \
             patch.object(config, "gemini_max_requests_per_minute", 100), \
             patch.object(config, "gemini_max_requests_per_hour", 100), \
             patch.object(config, "gemini_max_requests_per_day", 5):

            self.governor.requests_today = 5
            allowed, reason = self.governor.can_call_gemini()
            self.assertFalse(allowed)
            self.assertIn("Daily budget reached", reason)

    def test_circuit_breaker_on_rate_limit(self):
        """When 429 occurs, circuit breaker trips and suspends Gemini calls for cooldown period."""
        self.governor.trip_circuit_breaker("HTTP 429: Too Many Requests", cooldown_seconds=60.0)
        self.assertTrue(self.governor.circuit_breaker_active)

        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"):

            allowed, reason = self.governor.can_call_gemini()
            self.assertFalse(allowed)
            self.assertIn("Circuit breaker active", reason)

    def test_prompt_response_caching(self):
        """Identical prompts return cached responses without calling Gemini."""
        prompt = "Explain quantum computing in one sentence."
        sys_prompt = "You are a physics teacher."
        cached_resp = "Quantum computing harnesses superposition and entanglement for computation."

        self.governor.put_cached_response(prompt, sys_prompt, cached_resp)
        result = self.governor.get_cached_response(prompt, sys_prompt)

        self.assertEqual(result, cached_resp)

        # Non-matching prompt returns None
        self.assertIsNone(self.governor.get_cached_response("Different prompt", sys_prompt))

    def test_consultant_seamless_fallback_to_ollama(self):
        """LLMConsultant routes seamlessly to local Ollama when Gemini is throttled."""
        consultant = LLMConsultant(governor=self.governor)

        # Force governor to throttle
        self.governor.trip_circuit_breaker("Testing cooldown", cooldown_seconds=300.0)

        with patch.object(consultant, "_query_ollama", return_value="Local Ollama Response") as mock_ollama, \
             patch.object(consultant, "_query_gemini") as mock_gemini:

            resp = consultant.consult("Design a mobile motion pipeline")
            self.assertEqual(resp, "Local Ollama Response")
            mock_ollama.assert_called_once()
            mock_gemini.assert_not_called()

    def test_consultant_trips_circuit_breaker_on_http_429(self):
        """When Gemini returns HTTP 429, consultant trips circuit breaker and falls back to Ollama."""
        consultant = LLMConsultant(governor=self.governor)

        with patch.object(config, "gemini_enabled", True), \
             patch.object(config, "gemini_api_key", "fake-key"), \
             patch.object(self.governor, "can_call_gemini", return_value=(True, "OK")), \
             patch.object(consultant, "_query_gemini", side_effect=urllib.error.HTTPError(None, 429, "Too Many Requests", None, None)), \
             patch.object(consultant, "_query_ollama", return_value="Ollama Fallback Result") as mock_ollama:

            resp = consultant.consult("Complex architecture inquiry")
            self.assertEqual(resp, "Ollama Fallback Result")
            self.assertTrue(self.governor.circuit_breaker_active)
            self.assertIn("429", self.governor.circuit_breaker_reason)


if __name__ == "__main__":
    unittest.main()
