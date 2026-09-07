import logging
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ..scheduler import ScheduledTask

logger = logging.getLogger("Adrastea.Alpha.Goals.Base")


@dataclass
class BaseGoal(ABC):
    """Abstract Base Class for System Alpha's autonomous goals."""
    goal_id: str
    name: str
    description: str
    enabled: bool = True
    weight: float = 1.0              # Priority multiplier tweakable by Beta (higher = higher priority tasks)
    interval_seconds: float = 300.0  # How often this goal generates/triggers work
    last_run_time: float = 0.0
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=lambda: {
        "execution_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "last_result": "initialized",
        "last_updated": time.time()
    })

    def is_due(self, now: Optional[float] = None) -> bool:
        if not self.enabled:
            return False
        current = now if now is not None else time.time()
        return (current - self.last_run_time) >= self.interval_seconds

    def mark_executed(self) -> None:
        self.last_run_time = time.time()
        self.metrics["execution_count"] += 1
        self.metrics["last_updated"] = self.last_run_time

    def tune(self, updates: Dict[str, Any]) -> None:
        """Tweak goal parameters, weight, or interval (called by Beta)."""
        if "weight" in updates:
            old_w = self.weight
            self.weight = float(updates["weight"])
            logger.info(f"Goal [{self.goal_id}] weight tuned: {old_w} -> {self.weight}")

        if "enabled" in updates:
            self.enabled = bool(updates["enabled"])
            logger.info(f"Goal [{self.goal_id}] enabled state set to: {self.enabled}")

        if "interval_seconds" in updates:
            old_i = self.interval_seconds
            self.interval_seconds = float(updates["interval_seconds"])
            logger.info(f"Goal [{self.goal_id}] interval tuned: {old_i}s -> {self.interval_seconds}s")

        if "parameters" in updates and isinstance(updates["parameters"], dict):
            self.parameters.update(updates["parameters"])
            logger.info(f"Goal [{self.goal_id}] parameters updated: {updates['parameters']}")

    @abstractmethod
    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        """Synthesize concrete executable ScheduledTask objects to advance this goal."""
        pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "weight": round(self.weight, 3),
            "interval_seconds": self.interval_seconds,
            "last_run_time": self.last_run_time,
            "parameters": self.parameters,
            "metrics": self.metrics,
        }
