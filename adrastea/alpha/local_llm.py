import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

logger = logging.getLogger("Adrastea.Alpha.LocalLLM")


class LocalLLMClient:
    """Fast, deterministic interface to Ollama for System Alpha."""

    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "qwen3-coder:30b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        """Check if local Ollama service is reachable."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(self, prompt: str, system: Optional[str] = None, temperature: float = 0.2, timeout: int = 45) -> Optional[str]:
        """Generate deterministic text using local Ollama model."""
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        if system:
            payload["system"] = system

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("response", "").strip()
        except Exception as e:
            logger.warning(f"Local LLM generate failed: {e}")
            return None

    def classify_outcome(self, task_name: str, exit_code: int, output_sample: str) -> Dict[str, Any]:
        """Quickly classify a task outcome into score and diagnosis using the local LLM."""
        prompt = (
            f"Analyze this task execution:\n"
            f"Task: {task_name}\n"
            f"Exit Code: {exit_code}\n"
            f"Output Sample: {output_sample[:500]}\n\n"
            f"Respond with JSON format strictly containing:\n"
            f'{{"status": "SUCCESS" | "WARNING" | "FAILURE", "score_delta": -1.0 to 1.0, "summary": "one sentence"}}\n'
            f"JSON:"
        )
        resp = self.generate(prompt, system="You are an autonomous execution evaluator. Return valid JSON only.", temperature=0.0)
        if resp:
            try:
                # Clean code blocks if model included them
                resp_clean = resp.strip().strip("`")
                if resp_clean.startswith("json"):
                    resp_clean = resp_clean[4:].strip()
                return json.loads(resp_clean)
            except Exception:
                pass
        
        # Fallback deterministic evaluation
        score_delta = 1.0 if exit_code == 0 else -1.0
        return {
            "status": "SUCCESS" if exit_code == 0 else "FAILURE",
            "score_delta": score_delta,
            "summary": f"Deterministic eval: process exited with code {exit_code}"
        }
