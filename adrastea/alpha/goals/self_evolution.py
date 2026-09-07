import logging
import sys
import time
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.SelfEvolution")


class AdrasteaSelfEvolutionGoal(BaseGoal):
    """Goal 1: Continuous self-improvement, repo analysis, test health, and project visibility."""

    def __init__(self):
        super().__init__(
            goal_id="adrastea_self_evolution",
            name="Adrastea Self-Improvement & Repository Growth",
            description="Analyzes the Adrastea codebase, runs automated self-tests, audits documentation and visibility, and formulates repository enhancements.",
            enabled=True,
            weight=1.2,
            interval_seconds=300.0,
            parameters={
                "auto_test_enabled": True,
                "visibility_audit_enabled": True,
                "test_suite_path": "tests",
                "target_branch": "master",
            },
        )

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = time.time()
        tasks: List[ScheduledTask] = []
        base_priority = int(15 * self.weight)

        # 1. Codebase & Git Health Audit Task
        cmd_audit = (
            f'"{sys.executable}" -c '
            '"import subprocess, json, os; '
            'git_status = subprocess.run([\'git\', \'status\', \'--short\'], capture_output=True, text=True).stdout.strip(); '
            'commits = subprocess.run([\'git\', \'log\', \'-n\', \'1\', \'--oneline\'], capture_output=True, text=True).stdout.strip(); '
            'print(f\'ADRASTEA_REPO_AUDIT: Clean={not bool(git_status)} | LastCommit={commits} | Unstaged={len(git_status.splitlines()) if git_status else 0}\')"'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"self_repo_audit_{int(now)}",
                command=cmd_audit,
                priority=base_priority,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "intent": "Repository Health Audit"},
            )
        )

        # 2. Automated Regression / Stability Test (if enabled)
        if self.parameters.get("auto_test_enabled", True):
            cmd_test = (
                f'"{sys.executable}" -m unittest discover -s tests'
            )
            tasks.append(
                ScheduledTask(
                    task_id=f"self_regression_test_{int(now)}",
                    command=cmd_test,
                    priority=base_priority + 5,
                    interval_seconds=None,
                    metadata={"goal_id": self.goal_id, "intent": "Autonomous Code Verification"},
                )
            )

        # 3. Documentation & Visibility Audit (Checking README completeness & release readiness)
        if self.parameters.get("visibility_audit_enabled", True):
            cmd_docs = (
                f'"{sys.executable}" -c '
                '"from pathlib import Path; '
                'root = Path(r\'' + str(config.root_dir) + '\'); '
                'readme = (root / \'README.md\').exists(); '
                'act_log = (root / \'ACTIVITY_LOG.md\').exists(); '
                'directives = (root / \'DIRECTIVES.txt\').exists(); '
                'print(f\'VISIBILITY_AUDIT: README={readme}, ACTIVITY_LOG={act_log}, DIRECTIVES={directives}\')"'
            )
            tasks.append(
                ScheduledTask(
                    task_id=f"self_visibility_audit_{int(now)}",
                    command=cmd_docs,
                    priority=base_priority,
                    interval_seconds=None,
                    metadata={"goal_id": self.goal_id, "intent": "Project Visibility & Documentation Verification"},
                )
            )

        self.mark_executed()
        return tasks
