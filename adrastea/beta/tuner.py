import logging
from typing import Any, Dict, List, Optional
from ..ipc.protocol import Message, SignalType

logger = logging.getLogger("Adrastea.Beta.Tuner")


class HeuristicTuner:
    """Oversees Alpha's RL planner and autonomous goal hierarchy, dynamically tuning weights and parameters."""

    def __init__(self):
        self.optimization_count = 0
        self.goal_tuning_count = 0

    def evaluate_telemetry(self, telemetry: Dict[str, Any]) -> Optional[Message]:
        """Analyze Alpha's performance telemetry and generate RL weight adjustments."""
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

    def evaluate_goals(
        self,
        telemetry: Dict[str, Any],
        goals_data: Dict[str, Any],
        recent_directive: Optional[str] = None
    ) -> List[Message]:
        """Cognitively tunes Alpha's autonomous goals based on operational context, stability, and directives."""
        signals: List[Message] = []
        goals = goals_data.get("goals", {})
        if not goals:
            return signals

        # 1. Directive Steering: If Luke gave a directive mentioning a specific companion repo
        if recent_directive:
            directive_lower = recent_directive.lower()
            for repo in ["speech-flow", "interpretive-interface", "distributed-content-management"]:
                if repo in directive_lower or repo.replace("-", " ") in directive_lower:
                    logger.info(f"Directive alignment: Steering ecosystem_repos goal to focus on [{repo}]")
                    signals.append(
                        Message(
                            signal=SignalType.SIG_TUNE_GOALS,
                            sender="Beta",
                            payload={
                                "goal_id": "ecosystem_repos",
                                "weight": 2.5,
                                "parameters": {"focus_repo": repo},
                            }
                        )
                    )

        # 2. Stability / Idle Compute Allocation:
        # If Alpha is stable (low failures), boost companion ecosystem development and self-evolution
        total_exec = telemetry.get("total_executions", 0)
        total_fail = telemetry.get("total_failures", 0)
        failure_rate = total_fail / max(1, total_exec)

        if total_exec > 5 and failure_rate < 0.1:
            eco_goal = goals.get("ecosystem_repos", {})
            if eco_goal.get("weight", 1.0) < 1.6:
                logger.info("Cognitive tuning: System stable. Boosting ecosystem_repos and self_evolution goals.")
                signals.append(
                    Message(
                        signal=SignalType.SIG_TUNE_GOALS,
                        sender="Beta",
                        payload={"goal_id": "ecosystem_repos", "weight": 1.8}
                    )
                )
                signals.append(
                    Message(
                        signal=SignalType.SIG_TUNE_GOALS,
                        sender="Beta",
                        payload={"goal_id": "adrastea_self_evolution", "weight": 1.5}
                    )
                )

        # 3. Knowledge Graph Memory Consolidation Steering:
        kg_goal = goals.get("knowledge_graph_memory", {})
        # If tasks have executed heavily, accelerate memory consolidation interval
        if total_exec > 20 and kg_goal.get("interval_seconds", 180.0) > 120.0:
            logger.info("Cognitive tuning: High execution volume. Accelerating knowledge graph consolidation.")
            signals.append(
                Message(
                    signal=SignalType.SIG_TUNE_GOALS,
                    sender="Beta",
                    payload={
                        "goal_id": "knowledge_graph_memory",
                        "interval_seconds": 90.0,
                        "parameters": {"consolidation_decay_rate": 0.80}
                    }
                )
            )

        if signals:
            self.goal_tuning_count += len(signals)

        return signals
