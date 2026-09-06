import logging
from typing import Any, Dict, Optional
from ..ipc.protocol import Message, SignalType

logger = logging.getLogger("Adrastea.Beta.Tuner")


class HeuristicTuner:
    """Oversees Alpha's RL planner like a pathfinding cartographer and tunes scoring weights."""

    def __init__(self):
        self.optimization_count = 0

    def evaluate_telemetry(self, telemetry: Dict[str, Any]) -> Optional[Message]:
        """Analyze Alpha's performance telemetry and generate weight adjustments."""
        task_scores = telemetry.get("task_scores", {})
        total_exec = telemetry.get("total_executions", 0)
        total_fail = telemetry.get("total_failures", 0)
        current_weights = telemetry.get("weights", {})

        if total_exec < 3:
            return None  # Wait for baseline data

        failure_rate = total_fail / max(1, total_exec)
        new_weights: Dict[str, float] = {}

        # 1. High failure rate -> Increase penalty weights to avoid risky paths
        if failure_rate > 0.3:
            new_weights["w_error_penalty"] = min(30.0, current_weights.get("w_error_penalty", 15.0) + 2.0)
            new_weights["exploration_rate"] = max(0.05, current_weights.get("exploration_rate", 0.15) - 0.02)
            logger.info("Pathfinding heuristic: Elevated failure rate detected. Increasing error penalties.")

        # 2. High success rate & stability -> Encourage exploration of new workflows
        elif failure_rate < 0.05 and total_exec > 10:
            new_weights["exploration_rate"] = min(0.35, current_weights.get("exploration_rate", 0.15) + 0.05)
            logger.info("Pathfinding heuristic: System stable. Increasing exploration rate for novel discovery.")

        # 3. Check latency of tasks
        avg_durations = [m.get("avg_duration_seconds", 0) for m in task_scores.values()]
        if avg_durations and (sum(avg_durations) / len(avg_durations)) > 15.0:
            new_weights["w_latency_penalty"] = min(2.0, current_weights.get("w_latency_penalty", 0.5) + 0.2)
            logger.info("Pathfinding heuristic: Long execution times detected. Increasing latency penalties.")

        if new_weights:
            self.optimization_count += 1
            return Message(
                signal=SignalType.SIG_TUNE_WEIGHTS,
                sender="Beta",
                payload={"weights": new_weights}
            )

        return None
