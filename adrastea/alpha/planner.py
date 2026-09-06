import json
import logging
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from .runner import TaskExecutionResult

logger = logging.getLogger("Adrastea.Alpha.Planner")


@dataclass
class RLWeights:
    """Tuning weights adjustable by System Beta."""
    w_success: float = 10.0
    w_latency_penalty: float = 0.5
    w_error_penalty: float = 15.0
    w_consecutive_fail_penalty: float = 5.0
    exploration_rate: float = 0.15  # Epsilon for exploration vs exploitation
    discount_factor: float = 0.85   # Gamma


@dataclass
class TaskMetrics:
    task_name: str
    q_score: float = 50.0  # Initial baseline score
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0
    avg_duration_seconds: float = 0.0
    last_reward: float = 0.0


class RLPlanner:
    """Reinforcement learning guided execution planner for System Alpha.
    
    Scores outcomes, updates Q-values for task pathways, and allows System Beta
    to tune heuristic weights like a high-level pathfinding overseer.
    """

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file
        self.weights = RLWeights()
        self.task_scores: Dict[str, TaskMetrics] = {}
        self.history_rewards: List[float] = []

    def get_or_create_metrics(self, task_name: str) -> TaskMetrics:
        if task_name not in self.task_scores:
            self.task_scores[task_name] = TaskMetrics(task_name=task_name)
        return self.task_scores[task_name]

    def tune_weights(self, new_weights: Dict[str, float]) -> None:
        """Called when System Beta sends SIG_TUNE_WEIGHTS."""
        for k, v in new_weights.items():
            if hasattr(self.weights, k):
                old_val = getattr(self.weights, k)
                setattr(self.weights, k, float(v))
                logger.info(f"Tuned RL weight '{k}': {old_val} -> {v}")

    def compute_reward(self, result: TaskExecutionResult) -> float:
        """Calculate the scalar reward for a task outcome based on current weights."""
        metrics = self.get_or_create_metrics(result.task_id)

        if result.is_success:
            # Positive reward, discounted by latency
            reward = self.weights.w_success - (result.duration_seconds * self.weights.w_latency_penalty)
            metrics.consecutive_failures = 0
        else:
            # Negative reward penalized by error and consecutive failure counts
            metrics.consecutive_failures += 1
            reward = -(self.weights.w_error_penalty + (metrics.consecutive_failures * self.weights.w_consecutive_fail_penalty))

        return round(reward, 3)

    def record_outcome(self, result: TaskExecutionResult, external_score_delta: float = 0.0) -> float:
        """Update Q-scores for a completed task execution."""
        metrics = self.get_or_create_metrics(result.task_id)
        reward = self.compute_reward(result) + external_score_delta

        metrics.execution_count += 1
        if result.is_success:
            metrics.success_count += 1
        else:
            metrics.failure_count += 1

        # Moving average duration
        prev_dur = metrics.avg_duration_seconds
        metrics.avg_duration_seconds = round(((prev_dur * (metrics.execution_count - 1)) + result.duration_seconds) / metrics.execution_count, 3)

        # Temporal Difference Q-learning update step
        learning_rate = 0.2
        metrics.q_score = round(metrics.q_score + learning_rate * (reward - metrics.q_score), 3)
        metrics.last_reward = reward
        self.history_rewards.append(reward)

        logger.info(f"RL update for [{result.task_id}]: Reward={reward}, New Q-Score={metrics.q_score}")
        return reward

    def prioritize_tasks(self, candidate_task_names: List[str]) -> List[str]:
        """Rank and prioritize candidate tasks based on Q-scores and exploration."""
        if not candidate_task_names:
            return []

        # Epsilon-greedy exploration
        if random.random() < self.weights.exploration_rate:
            shuffled = list(candidate_task_names)
            random.shuffle(shuffled)
            return shuffled

        # Exploit highest Q-score
        def score_key(name: str) -> float:
            m = self.task_scores.get(name)
            return m.q_score if m else 50.0

        return sorted(candidate_task_names, key=score_key, reverse=True)

    def is_stuck(self, task_name: str, threshold_consecutive_fails: int = 3) -> bool:
        """Check if a task is experiencing repeated failure states."""
        m = self.task_scores.get(task_name)
        return bool(m and m.consecutive_failures >= threshold_consecutive_fails)

    def get_summary_telemetry(self) -> Dict[str, Any]:
        """Aggregate telemetry for Beta."""
        return {
            "task_scores": {k: asdict(v) for k, v in self.task_scores.items()},
            "weights": asdict(self.weights),
            "total_executions": sum(m.execution_count for m in self.task_scores.values()),
            "total_successes": sum(m.success_count for m in self.task_scores.values()),
            "total_failures": sum(m.failure_count for m in self.task_scores.values()),
        }
