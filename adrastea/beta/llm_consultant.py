import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional
from ..config import config

logger = logging.getLogger("Adrastea.Beta.LLM")


class LLMConsultant:
    """Consults external frontier models (Google Gemini) or local LLMs (via Ollama/MCP)
    based on task complexity and operator preferences.
    """

    def __init__(self):
        self.gemini_key = config.gemini_api_key
        self.gemini_model = config.gemini_model
        self.ollama_url = config.ollama_base_url
        self.ollama_model = config.ollama_model

    def consult(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 1024,
        preferred_provider: str = "auto",
    ) -> str:
        """Query LLM with preferred provider routing:
        - "auto": Tries Gemini first if key available; falls back seamlessly to local LLM via MCP/Ollama.
        - "gemini": Strictly calls Gemini with fallback to local LLM on error.
        - "local_mcp": Prioritizes local Ollama inference via MCP; falls back to Gemini if local fails.
        """
        # 1. If local_mcp preferred
        if preferred_provider == "local_mcp":
            local_resp = self._query_ollama(prompt, system_prompt)
            if local_resp and not local_resp.startswith("Adrastea reasoning fallback"):
                return local_resp
            logger.info("Local LLM unavailable or failed; falling back to Gemini...")
            if self.gemini_key:
                gemini_resp = self._query_gemini(prompt, system_prompt)
                if gemini_resp:
                    return gemini_resp
            return local_resp

        # 2. Standard / Auto routing: Attempt Gemini if key is provided
        if self.gemini_key:
            try:
                resp = self._query_gemini(prompt, system_prompt)
                if resp:
                    return resp
            except Exception as e:
                logger.warning(f"Gemini consultation failed: {e}. Falling back to local Ollama...")

        # 3. Fallback to local Ollama
        return self._query_ollama(prompt, system_prompt)

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
