import json
import logging
import sys
import time
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from ..solved_problems import (
    AUTHORIZED_OPERATOR,
    TARGET_REPOS,
    apply_code_patch,
    create_feature_branch_and_commit,
    fetch_repo_issues,
    inspect_repository,
    loop_target_repositories_step,
    post_progress_and_pause,
    push_and_open_pull_request,
    run_tests,
)
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.RepoFeatureExecutor")


class RepoFeatureExecutorGoal(BaseGoal):
    """Goal 8: Autonomous Target Repository Feature Execution & Solved Problems Loop.
    Loops through target repositories, inspects environment and .adrastea.json configs,
    identifies issues and operator directives, and executes features offloading procedural
    tasks to Alpha's Solved Problems.
    """

    def __init__(self):
        super().__init__(
            goal_id="repo_feature_executor",
            name="Target Repository Feature Execution & Solved Problems Loop",
            description=(
                "Loops through target repos (Adrastea, hardcode, speech-flow, market-research, interpretive-interface, "
                "distributed-content-management), reads repo configs and issue directives, offloads procedural tasks "
                "as Solved Problems to Alpha, executes features, and pauses for Luke's guidance."
            ),
            enabled=True,
            weight=1.5,
            interval_seconds=300.0,  # 5-minute cycle
            parameters={
                "target_repos": TARGET_REPOS,
                "focus_repo": None,
                "assignee": AUTHORIZED_OPERATOR,
                "auto_pr": True,
            },
        )
        self._current_index = 0

    def _select_repo(self) -> str:
        repos = self.parameters.get("target_repos", TARGET_REPOS)
        focus = self.parameters.get("focus_repo")
        if focus and focus in repos:
            return focus
        selected = repos[self._current_index % len(repos)]
        self._current_index += 1
        return selected

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = (context.get("now") if context and "now" in context else time.time())
        tasks: List[ScheduledTask] = []
        base_priority = int(25 * self.weight)

        target_repo = self._select_repo()
        clean_repo_id = target_repo.replace("-", "_")

        # Task 1: Repository inspection & issue actionable queue gathering
        cmd_inspect = (
            f'"{sys.executable}" -m adrastea.alpha.solved_problems inspect {target_repo}'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"repo_exec_inspect_{clean_repo_id}_{int(now)}",
                command=cmd_inspect,
                priority=base_priority,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Target Repository Solved Problems Inspection",
                },
            )
        )

        # Task 2: Full snapshot and loop through all target repositories
        cmd_loop = (
            f'"{sys.executable}" -m adrastea.alpha.solved_problems loop'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"repo_exec_loop_all_{int(now)}",
                command=cmd_loop,
                priority=base_priority + 5,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Target Repositories Full Loop Snapshot",
                },
            )
        )

        # Task 2: Automated test execution & verification for target repository
        cmd_test = (
            f'"{sys.executable}" -m adrastea.alpha.solved_problems test {target_repo}'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"repo_exec_test_{clean_repo_id}_{int(now)}",
                command=cmd_test,
                priority=base_priority + 2,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Target Repository Autonomous Test Verification",
                },
            )
        )

        # Task 3: Autonomous Pull Request Verification & Merge
        cmd_merge = (
            f'"{sys.executable}" -m adrastea.alpha.solved_problems merge {target_repo}'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"repo_exec_merge_{clean_repo_id}_{int(now)}",
                command=cmd_merge,
                priority=base_priority + 4,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Target Repository Autonomous PR Merge",
                },
            )
        )

        # Task 4: Autonomous Guidance & Issue Self-Direction (10-Minute Timeout)
        cmd_steer = (
            f'"{sys.executable}" -m adrastea.alpha.solved_problems auto-steer {target_repo}'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"repo_exec_steer_{clean_repo_id}_{int(now)}",
                command=cmd_steer,
                priority=base_priority + 1,
                interval_seconds=None,
                metadata={
                    "goal_id": self.goal_id,
                    "repo": target_repo,
                    "intent": "Target Repository Autonomous Issue Steering & Gemini Guidance",
                },
            )
        )

        self.mark_executed()
        return tasks
