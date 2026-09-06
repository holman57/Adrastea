import datetime
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import config

logger = logging.getLogger("Adrastea.ActivityLogger")


class ActivityLogger:
    """Maintains ACTIVITY_LOG.md in the repo and periodically commits it to GitHub."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or (config.root_dir / "ACTIVITY_LOG.md")
        self.last_commit_time = 0.0
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if not self.log_path.exists():
            header = (
                "# Adrastea Autonomous Activity Log\n\n"
                "This log records autonomous operational cycles, task executions, RL Q-scores, "
                "outreach attempts, and directives requested from Luke Holman (@holman57).\n\n"
                "---\n\n"
            )
            with open(self.log_path, "w", encoding="utf-8") as f:
                f.write(header)

    def log_cycle(
        self,
        alpha_status: Dict[str, Any],
        beta_action: str,
        outreach_results: Dict[str, Any],
        pending_directive_prompt: str
    ) -> None:
        """Append a structured cycle entry to ACTIVITY_LOG.md."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = alpha_status.get("uptime_seconds", 0)
        telemetry = alpha_status.get("telemetry", {})
        total_exec = telemetry.get("total_executions", 0)
        total_succ = telemetry.get("total_successes", 0)
        total_fail = telemetry.get("total_failures", 0)
        active_tasks = alpha_status.get("active_tasks", [])

        # Format outreach summary
        contact_summary = []
        for channel, res in outreach_results.items():
            status_str = "OK" if res.get("success") else "FAILED"
            contact_summary.append(f"- **{channel}**: {status_str} ({res.get('details', '')})")
        contact_block = "\n".join(contact_summary) if contact_summary else "- No outreach triggered this cycle."

        entry = (
            f"### [{now}] Autonomous Cycle Report\n\n"
            f"- **System State**: Alpha Uptime: {uptime}s | Active Tasks: {len(active_tasks)}\n"
            f"- **Execution Metrics**: {total_succ} Successes, {total_fail} Failures (Total: {total_exec})\n"
            f"- **Beta Cognitive Action**: {beta_action}\n"
            f"- **Outreach Attempts**:\n{contact_block}\n"
            f"- **Direction Prompt for Luke**:\n> {pending_directive_prompt}\n\n"
            f"---\n\n"
        )

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info(f"Recorded cycle update in {self.log_path.name}")
        except Exception as e:
            logger.error(f"Failed writing to activity log: {e}")

    def commit_and_push(self, force: bool = False, min_interval_seconds: float = 600.0) -> bool:
        """Commit ACTIVITY_LOG.md and push to GitHub repository."""
        now = time.time()
        if not force and (now - self.last_commit_time) < min_interval_seconds:
            return False

        logger.info("Committing and pushing updated ACTIVITY_LOG.md to GitHub...")
        try:
            # Stage only ACTIVITY_LOG.md to prevent any accidental leakage
            subprocess.run(["git", "add", str(self.log_path)], cwd=str(config.root_dir), check=True, capture_output=True)
            
            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            commit_msg = f"docs(activity): autonomous update [{timestamp_str}]"
            
            commit_res = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(config.root_dir),
                capture_output=True,
                text=True
            )
            if "nothing to commit" in commit_res.stdout or "nothing to commit" in commit_res.stderr:
                logger.info("No activity log changes to commit.")
                return False

            push_res = subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(config.root_dir),
                capture_output=True,
                text=True,
                check=True
            )
            self.last_commit_time = now
            logger.info(f"Successfully pushed activity log to GitHub: {commit_msg}")
            return True
        except Exception as e:
            logger.error(f"Failed to commit and push activity log: {e}")
            return False
