import logging
import time
from typing import Any, Dict, List, Optional

from ..scheduler import ScheduledTask
from .base import BaseGoal
from .companion_feature_builder import CompanionFeatureBuilderGoal
from .daily_github_commit import DailyGitHubCommitGoal
from .ecosystem_repos import EcosystemReposGoal
from .knowledge_graph import KnowledgeGraphMemoryGoal
from .self_evolution import AdrasteaSelfEvolutionGoal
from .user_coordination import UserCoordinationGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.Manager")


class GoalManager:
    """Manages Alpha's autonomous goal hierarchy and handles parameter tuning from System Beta."""

    def __init__(self):
        self.goals: Dict[str, BaseGoal] = {}
        self._register_default_goals()

    def _register_default_goals(self) -> None:
        """Register the foundational autonomous goals."""
        self.register_goal(AdrasteaSelfEvolutionGoal())
        self.register_goal(UserCoordinationGoal())
        self.register_goal(EcosystemReposGoal())
        self.register_goal(KnowledgeGraphMemoryGoal())
        self.register_goal(DailyGitHubCommitGoal())
        self.register_goal(CompanionFeatureBuilderGoal())

    def register_goal(self, goal: BaseGoal) -> None:
        self.goals[goal.goal_id] = goal
        logger.info(f"Registered autonomous goal [{goal.goal_id}]: {goal.name} (Weight: {goal.weight})")

    def get_goal(self, goal_id: str) -> Optional[BaseGoal]:
        return self.goals.get(goal_id)

    def tune_goal(self, goal_id: str, updates: Dict[str, Any]) -> bool:
        """Tweaks an existing goal's weight, enabled state, interval, or domain parameters."""
        goal = self.goals.get(goal_id)
        if not goal:
            logger.warning(f"Cannot tune unknown goal [{goal_id}]")
            return False
        goal.tune(updates)
        return True

    def generate_due_tasks(self, now: Optional[float] = None) -> List[ScheduledTask]:
        """Scans all registered goals, generating tasks for due goals ordered by goal weight."""
        current = now if now is not None else time.time()
        due_goals = [g for g in self.goals.values() if g.is_due(current)]

        # Sort due goals by weight descending (higher weight goals generate tasks first)
        due_goals.sort(key=lambda g: g.weight, reverse=True)

        generated_tasks: List[ScheduledTask] = []
        for g in due_goals:
            try:
                tasks = g.generate_tasks()
                generated_tasks.extend(tasks)
                logger.info(f"Goal [{g.goal_id}] generated {len(tasks)} tasks.")
            except Exception as e:
                logger.error(f"Error generating tasks for goal [{g.goal_id}]: {e}", exc_info=True)

        return generated_tasks

    def record_task_outcome(self, goal_id: str, success: bool) -> None:
        """Updates goal metrics when a task associated with the goal finishes."""
        goal = self.goals.get(goal_id)
        if goal:
            if success:
                goal.metrics["success_count"] += 1
                goal.metrics["last_result"] = "success"
            else:
                goal.metrics["failure_count"] += 1
                goal.metrics["last_result"] = "failed"
            goal.metrics["last_updated"] = time.time()

    def get_goals_status(self) -> Dict[str, Any]:
        """Provides a complete status dictionary of all goals for telemetry and Beta tuning."""
        return {
            "total_goals": len(self.goals),
            "enabled_goals": sum(1 for g in self.goals.values() if g.enabled),
            "goals": {gid: g.to_dict() for gid, g in self.goals.items()},
            "timestamp": time.time(),
        }
