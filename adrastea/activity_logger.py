import datetime
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from .config import config
from .sanitizer import sanitize_text

logger = logging.getLogger("Adrastea.ActivityLogger")


class ActivityLogger:
    """Maintains ACTIVITY_LOG.md locally and commits to GitHub only upon significant happenings."""

    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path or (config.root_dir / "ACTIVITY_LOG.md")
        self.last_push_time = 0.0
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
        outreach_results: Optional[Dict[str, Any]] = None,
        pending_directive_prompt: Optional[str] = None
    ) -> None:
        """Append a structured cycle entry to the local ACTIVITY_LOG.md."""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uptime = alpha_status.get("uptime_seconds", 0)
        telemetry = alpha_status.get("telemetry", {})
        total_exec = telemetry.get("total_executions", 0)
        total_succ = telemetry.get("total_successes", 0)
        total_fail = telemetry.get("total_failures", 0)
        active_tasks = alpha_status.get("active_tasks", [])

        contact_block = ""
        if outreach_results:
            contact_summary = []
            for channel, res in outreach_results.items():
                status_str = "OK" if res.get("success") else "FAILED"
                contact_summary.append(f"- **{channel}**: {status_str} ({res.get('details', '')})")
            contact_block = "- **Outreach Attempts**:\n" + "\n".join(contact_summary) + "\n"

        prompt_block = f"- **Direction Prompt for Luke**:\n> {pending_directive_prompt}\n" if pending_directive_prompt else ""

        entry = (
            f"### [{now}] Significant Event / Cycle Update\n\n"
            f"- **System State**: Alpha Uptime: {uptime}s | Active Tasks: {len(active_tasks)}\n"
            f"- **Execution Metrics**: {total_succ} Successes, {total_fail} Failures (Total: {total_exec})\n"
            f"- **Beta Action / Event**: {beta_action}\n"
            f"{contact_block}"
            f"{prompt_block}\n"
            f"---\n\n"
        )

        entry = sanitize_text(entry)

        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info(f"Recorded local activity entry: '{beta_action}'")
        except Exception as e:
            logger.error(f"Failed writing to activity log: {e}")

    def commit_and_push_significant_event(
        self,
        event_description: str,
        min_cooldown_seconds: float = 1800.0,
        bypass_cooldown: bool = False
    ) -> bool:
        """Commit ACTIVITY_LOG.md and push to GitHub ONLY for significant happenings.
        
        Pushes are event-driven (e.g. user directive adopted, stuck task triaged, major milestone)
        and throttled by cooldown to prevent relentless pushing.
        """
        now = time.time()
        time_since_last = now - self.last_push_time

        if not bypass_cooldown and time_since_last < min_cooldown_seconds:
            logger.info(
                f"Skipping Git push for '{event_description}' (Cooldown active: "
                f"{int(time_since_last)}s < {int(min_cooldown_seconds)}s)."
            )
            return False

        logger.info(f"Pushing significant happening to GitHub: '{event_description}'...")
        try:
            # Stage only ACTIVITY_LOG.md to guarantee no leakage of untracked files
            subprocess.run(["git", "add", str(self.log_path)], cwd=str(config.root_dir), check=True, capture_output=True)

            timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            commit_msg = f"docs(activity): {event_description} [{timestamp_str}]"

            commit_res = subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=str(config.root_dir),
                capture_output=True,
                text=True
            )
            if "nothing to commit" in commit_res.stdout or "nothing to commit" in commit_res.stderr:
                logger.info("No activity changes to commit.")
                return False

            subprocess.run(
                ["git", "push", "origin", "main"],
                cwd=str(config.root_dir),
                capture_output=True,
                text=True,
                check=True
            )
            self.last_push_time = now
            logger.info(f"Pushed significant event to GitHub: {commit_msg}")
            return True
        except Exception as e:
            logger.error(f"Failed to commit and push activity log: {e}")
            return False
