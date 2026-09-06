import json
import logging
from typing import Any, Dict, List, Optional
from ..ipc.protocol import Message, SignalType
from .llm_consultant import LLMConsultant

logger = logging.getLogger("Adrastea.Beta.Triage")


class TriageEngine:
    """Diagnoses and unblocks Alpha when it encounters unexpected errors or gets stuck."""

    def __init__(self, llm: LLMConsultant):
        self.llm = llm

    def analyze_stuck_state(self, stuck_payload: Dict[str, Any]) -> List[Message]:
        """Formulate corrective IPC signals to resolve Alpha's stuck state."""
        task_id = stuck_payload.get("task_id", "unknown")
        command = stuck_payload.get("command", "")
        consecutive_fails = stuck_payload.get("consecutive_failures", 0)
        last_error = stuck_payload.get("last_error", "")

        logger.warning(f"Triaging stuck task [{task_id}] (Fails: {consecutive_fails})")

        # Prompt LLM to diagnose root cause and recommend action
        prompt = (
            f"Alpha execution engine is STUCK on task [{task_id}].\n"
            f"Command: {command}\n"
            f"Consecutive Failures: {consecutive_fails}\n"
            f"Error Output: {last_error}\n\n"
            f"Select a remediation strategy:\n"
            f"1. Interrupt task and disable it\n"
            f"2. Mutate command or arguments\n"
            f"3. Increase penalty weight to steer RL pathfinding away\n"
            f"Reply with JSON: {{\"action\": \"INTERRUPT\"|\"MUTATE\"|\"TUNE\", \"reason\": \"...\", \"new_command\": \"...\" (optional)}}\n"
            f"JSON:"
        )

        llm_response = self.llm.consult(
            prompt=prompt,
            system_prompt="You are System Beta, an AI system engineer resolving system execution bottlenecks."
        )

        signals_to_send: List[Message] = []

        # Always interrupt the actively stuck task first to free resources
        signals_to_send.append(
            Message(
                signal=SignalType.SIG_INTERRUPT,
                sender="Beta",
                payload={"task_id": task_id, "reason": f"Repeated failures ({consecutive_fails})"}
            )
        )

        # Heavily penalize this failing task in the RL planner so Alpha avoids it
        signals_to_send.append(
            Message(
                signal=SignalType.SIG_TUNE_WEIGHTS,
                sender="Beta",
                payload={"weights": {"w_error_penalty": 25.0, "w_consecutive_fail_penalty": 10.0}}
            )
        )

        # Parse LLM recommendation for additional mutation or corrective task
        try:
            clean = llm_response.strip().strip("`")
            if clean.startswith("json"):
                clean = clean[4:].strip()
            data = json.loads(clean)

            if data.get("action") == "MUTATE" and data.get("new_command"):
                signals_to_send.append(
                    Message(
                        signal=SignalType.SIG_MUTATE,
                        sender="Beta",
                        payload={"task_id": task_id, "updates": {"command": data["new_command"]}}
                    )
                )
        except Exception:
            pass

        return signals_to_send
