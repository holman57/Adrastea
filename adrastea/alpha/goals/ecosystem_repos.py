import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.Ecosystem")


class EcosystemReposGoal(BaseGoal):
    """Goal 3: Continuously inspect, diagnose, and advance companion AI-managed projects."""

    def __init__(self):
        super().__init__(
            goal_id="ecosystem_repos",
            name="Ecosystem Repository Development & AI Project Management",
            description="Supervises and advances unfinished companion AI-managed projects (speech-flow, interpretive-interface, distributed-content-management).",
            enabled=True,
            weight=1.1,
            interval_seconds=360.0,
            parameters={
                "target_repos": [
                    "distributed-content-management",
                    "interpretive-interface",
                    "speech-flow",
                    "hardcode",
                    "market-research",
                ],
                "focus_repo": None,  # If set, focuses tasks on this specific project
                "auto_diagnose_tests": True,
                "scan_missing_components": True,
            },
        )
        self._current_index = 0

    def _select_repo(self) -> str:
        repos = self.parameters.get("target_repos", ["speech-flow"])
        focus = self.parameters.get("focus_repo")
        if focus and focus in repos:
            return focus
        if not repos:
            return "speech-flow"
        selected = repos[self._current_index % len(repos)]
        self._current_index += 1
        return selected

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = time.time()
        tasks: List[ScheduledTask] = []
        base_priority = int(20 * self.weight)

        target_repo = self._select_repo()
        workspace = config.companion_workspace_dir
        repo_dir = workspace / target_repo

        # Task 1: Comprehensive Companion Repo Scan
        cmd_scan = (
            f'"{sys.executable}" -c '
            f'"import os, json; from pathlib import Path; '
            f'r = Path(r\'{repo_dir}\'); '
            f'exists = r.is_dir(); '
            f'items = [f.name for f in r.iterdir()] if exists else []; '
            f'has_readme = \'README.md\' in items; '
            f'has_tests = \'tests\' in items or (r / \'src\' / \'test\').exists(); '
            f'print(f\'ECOSYSTEM_SCAN: Repo={target_repo} | Exists={{exists}} | Files={{len(items)}} | HasTests={{has_tests}} | HasReadme={{has_readme}}\')"'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"eco_scan_{target_repo.replace('-', '_')}_{int(now)}",
                command=cmd_scan,
                priority=base_priority,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "repo": target_repo, "intent": "Repository Scan & Inventory"},
            )
        )

        # Task 2: Project-Specific Diagnostics
        if target_repo == "speech-flow":
            # Python test suite verification
            cmd_diag = (
                f'"{sys.executable}" -c '
                f'"import subprocess, sys; from pathlib import Path; '
                f'r = Path(r\'{repo_dir}\'); '
                f't = r / \'tests\'; '
                f'res = subprocess.run([sys.executable, \'-m\', \'unittest\', \'discover\', \'-s\', str(t)], cwd=str(r), capture_output=True, text=True) if t.is_dir() else None; '
                f'print(f\'SPEECH_FLOW_HEALTH: TestsPresent={{t.is_dir()}} | ReturnCode={{res.returncode if res else -1}}\')"'
            )
        elif target_repo == "interpretive-interface":
            # Kotlin / Gradle project check
            cmd_diag = (
                f'"{sys.executable}" -c '
                f'"from pathlib import Path; '
                f'r = Path(r\'{repo_dir}\'); '
                f'has_gradle = (r / \'build.gradle.kts\').exists() or (r / \'build.gradle\').exists(); '
                f'has_src = (r / \'src\').exists(); '
                f'print(f\'INTERPRETIVE_INTERFACE_HEALTH: GradleConfig={{has_gradle}} | SourceTree={{has_src}}\')"'
            )
        elif target_repo == "hardcode":
            # Flutter / Dart / python_driver check
            cmd_diag = (
                f'"{sys.executable}" -c '
                f'"from pathlib import Path; '
                f'r = Path(r\'{repo_dir}\'); '
                f'has_pubspec = (r / \'pubspec.yaml\').exists(); '
                f'has_db = (r / \'db_backup.json\').exists(); '
                f'has_driver = (r / \'python_driver.py\').exists(); '
                f'print(f\'HARDCODE_HEALTH: Pubspec={{has_pubspec}} | DBBackup={{has_db}} | Driver={{has_driver}}\')"'
            )
        elif target_repo == "market-research":
            # Web crawler & topic scoring engine check
            cmd_diag = (
                f'"{sys.executable}" -c '
                f'"from pathlib import Path; '
                f'r = Path(r\'{repo_dir}\'); '
                f'has_pkg = (r / \'pyproject.toml\').exists(); '
                f'has_src = (r / \'market_research\').exists(); '
                f'has_tests = (r / \'tests\').exists(); '
                f'print(f\'MARKET_RESEARCH_HEALTH: PyProject={{has_pkg}} | SourceTree={{has_src}} | Tests={{has_tests}}\')"'
            )
        else:
            # distributed-content-management (scaffold / architecture readiness check)
            cmd_diag = (
                f'"{sys.executable}" -c '
                f'"from pathlib import Path; '
                f'r = Path(r\'{repo_dir}\'); '
                f'has_src = (r / \'src\').exists() or (r / \'dcm\').exists(); '
                f'has_pkg = (r / \'package.json\').exists() or (r / \'pyproject.toml\').exists(); '
                f'print(f\'DISTRIBUTED_CONTENT_MGMT_HEALTH: SourceDir={{has_src}} | PackageDef={{has_pkg}}\')"'
            )

        tasks.append(
            ScheduledTask(
                task_id=f"eco_diag_{target_repo.replace('-', '_')}_{int(now)}",
                command=cmd_diag,
                priority=base_priority + 2,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "repo": target_repo, "intent": "Companion Project Diagnostics"},
            )
        )

        self.mark_executed()
        return tasks
