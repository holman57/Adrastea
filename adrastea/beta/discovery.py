import logging
import time
from typing import Any, Dict, List, Optional
from ..ipc.protocol import Message, SignalType
from .llm_consultant import LLMConsultant

logger = logging.getLogger("Adrastea.Beta.Discovery")


class GoalDiscovery:
    """Discovers new tasks, generates optimization goals, and formulates user inquiries."""

    def __init__(self, llm: LLMConsultant):
        self.llm = llm
        self.proposed_goals_count = 0

    def formulate_user_question(self, system_status: Dict[str, Any]) -> str:
        """Consults LLM to generate an insightful question for the user based on current system status."""
        uptime = system_status.get("uptime_seconds", 0)
        total_exec = system_status.get("telemetry", {}).get("total_executions", 0)

        prompt = (
            f"Adrastea has been running stably for {uptime} seconds with {total_exec} executions completed.\n"
            f"Generate a concise, thoughtful question asking the user for their next strategic goal or instructions.\n"
            f"Give 3 concrete recommended options (e.g. data scraping, performance benchmarking, local model fine-tuning, security audits).\n"
            f"Keep it under 3 sentences."
        )

        response = self.llm.consult(
            prompt=prompt,
            system_prompt="You are System Beta, the strategic mind of Adrastea. You are asking the user for operational direction."
        )
        return response or (
            "Adrastea is running stably in standby mode.\n"
            "Would you like me to: (1) Run continuous local model benchmarks, "
            "(2) Initialize an automated codebase review, or (3) Remain in low-power idle monitoring?"
        )

    def discover_novel_task(self, system_status: Dict[str, Any]) -> Optional[Message]:
        """Synthesize a new useful maintenance or diagnostic task for Alpha."""
        self.proposed_goals_count += 1
        task_id = f"discovery_task_{int(time.time())}"

        # Standard safe diagnostic task
        command = "python -c \"import psutil, sys; print(f'CPU: {psutil.cpu_percent()}%, Mem: {psutil.virtual_memory().percent}%')\""

        return Message(
            signal=SignalType.SIG_DISPATCH,
            sender="Beta",
            payload={
                "task_id": task_id,
                "command": command,
                "priority": 15,
                "metadata": {"discovered_by": "Beta.GoalDiscovery", "intent": "System Health Telemetry"}
            }
        )
