import time
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from .planner import RLPlanner

logger = logging.getLogger("Adrastea.Alpha.Scheduler")


@dataclass
class ScheduledTask:
    task_id: str
    command: str
    interval_seconds: Optional[float] = None  # None for one-shot
    next_run_time: float = field(default_factory=time.time)
    last_run_time: Optional[float] = None
    priority: int = 10
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_executed(self) -> None:
        self.last_run_time = time.time()
        if self.interval_seconds is not None and self.interval_seconds > 0:
            self.next_run_time = self.last_run_time + self.interval_seconds
        else:
            self.enabled = False  # Completed one-shot task


class TaskScheduler:
    """Deterministic Task Scheduler for System Alpha."""

    def __init__(self, planner: RLPlanner):
        self.planner = planner
        self.tasks: Dict[str, ScheduledTask] = {}

    def register(self, task: ScheduledTask) -> None:
        self.tasks[task.task_id] = task
        logger.info(f"Registered scheduled task [{task.task_id}] (Interval: {task.interval_seconds}s)")

    def dispatch(self, task_id: str, command: str, priority: int = 20, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Dispatches an immediate task (e.g. injected by Beta)."""
        task = ScheduledTask(
            task_id=task_id,
            command=command,
            interval_seconds=None,
            next_run_time=time.time() - 1.0,  # Immediately due
            priority=priority,
            enabled=True,
            metadata=metadata or {}
        )
        self.tasks[task_id] = task
        logger.info(f"Dispatched high-priority immediate task [{task_id}]: {command}")

    def mutate(self, task_id: str, updates: Dict[str, Any]) -> bool:
        """Mutates an existing scheduled task (e.g. from Beta)."""
        task = self.tasks.get(task_id)
        if not task:
            logger.warning(f"Cannot mutate non-existent task [{task_id}]")
            return False
        
        for k, v in updates.items():
            if hasattr(task, k):
                setattr(task, k, v)
                logger.info(f"Mutated task [{task_id}] attribute {k} = {v}")
        return True

    def cancel(self, task_id: str) -> bool:
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            logger.info(f"Cancelled task [{task_id}]")
            return True
        return False

    def get_due_tasks(self) -> List[ScheduledTask]:
        """Returns due tasks prioritized by the RL Planner and task priority."""
        now = time.time()
        due = [t for t in self.tasks.values() if t.enabled and t.next_run_time <= now]
        if not due:
            return []

        # Use RL planner to prioritize candidate task IDs
        candidate_ids = [t.task_id for t in due]
        ranked_ids = self.planner.prioritize_tasks(candidate_ids)

        # Order due tasks matching the ranked list
        id_to_task = {t.task_id: t for t in due}
        ordered = [id_to_task[tid] for tid in ranked_ids if tid in id_to_task]
        return ordered
