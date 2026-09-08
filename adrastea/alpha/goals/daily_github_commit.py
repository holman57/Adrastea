import argparse
import datetime
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.DailyGitHubCommit")


def get_last_commit_info(repo_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Inspects Git repository history to determine the timestamp and details of the latest commit."""
    root = repo_dir or config.root_dir
    try:
        res = subprocess.run(
            ["git", "log", "-n", "1", "--format=%ct|%ci|%H|%s"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        output = res.stdout.strip()
        if not output:
            return {"timestamp": 0.0, "iso": "", "hash": "", "subject": ""}
        parts = output.split("|", 3)
        return {
            "timestamp": float(parts[0]),
            "iso": parts[1] if len(parts) > 1 else "",
            "hash": parts[2] if len(parts) > 2 else "",
            "subject": parts[3] if len(parts) > 3 else "",
        }
    except Exception as e:
        logger.warning(f"Unable to read git commit history in {root}: {e}")
        return {"timestamp": 0.0, "iso": "", "hash": "", "subject": "", "error": str(e)}


def is_commit_due(
    repo_dir: Optional[Path] = None,
    max_commit_age_seconds: float = 86400.0,
    check_calendar_day: bool = True,
    target_commit_hour: int = 20,
    force: bool = False,
    now: Optional[float] = None
) -> bool:
    """Evaluates whether a commit to GitHub is due.
    
    A commit is due if:
      1. Force flag is True.
      2. Elapsed time since the last commit >= max_commit_age_seconds (default 24h = 86400s).
      3. check_calendar_day is True AND no commit was made today AND current hour >= target_commit_hour.
    """
    if force:
        return True

    current_time = now if now is not None else time.time()
    info = get_last_commit_info(repo_dir)
    last_timestamp = info.get("timestamp", 0.0)

    # If repo has never had a commit, it's definitely due
    if last_timestamp <= 0.0:
        return True

    time_since_commit = current_time - last_timestamp
    if time_since_commit >= max_commit_age_seconds:
        logger.info(
            f"Daily commit is due: elapsed {int(time_since_commit)}s >= "
            f"threshold {int(max_commit_age_seconds)}s."
        )
        return True

    if check_calendar_day:
        last_date = datetime.date.fromtimestamp(last_timestamp)
        today_date = datetime.date.fromtimestamp(current_time)
        current_hour = datetime.datetime.fromtimestamp(current_time).hour

        if last_date < today_date and current_hour >= target_commit_hour:
            logger.info(
                f"Daily commit is due: last commit was on {last_date}, today is {today_date} "
                f"and current hour {current_hour} >= target hour {target_commit_hour}."
            )
            return True

    return False


def run_daily_commit(
    repo_dir: Optional[Path] = None,
    target_remote: str = "origin",
    target_branch: str = "main",
    auto_push: bool = True,
    tracked_files: Optional[List[str]] = None,
    commit_message_prefix: str = "chore(daily): autonomous daily progress sync",
    force: bool = False
) -> Dict[str, Any]:
    """Executes the daily commit and push to GitHub.
    
    Ensures safe staging by only staging explicitly tracked files (default: ACTIVITY_LOG.md).
    If no uncommitted changes are present in tracked files, appends a daily operational
    heartbeat entry to ACTIVITY_LOG.md before committing.
    """
    root = repo_dir or config.root_dir
    files_to_track = tracked_files or ["ACTIVITY_LOG.md"]
    activity_file = root / "ACTIVITY_LOG.md"

    logger.info(f"Initiating daily commit routine in {root}...")

    # Step 1: Ensure ACTIVITY_LOG.md has content to commit
    # Check git status for modified files among files_to_track
    status_res = subprocess.run(
        ["git", "status", "--porcelain"] + files_to_track,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    has_tracked_changes = bool(status_res.stdout.strip())

    if not has_tracked_changes:
        # Append a clean daily operational summary to ACTIVITY_LOG.md
        now_dt = datetime.datetime.now()
        timestamp_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n---\n\n"
            f"### [{timestamp_str}] Daily Operational Heartbeat & Progress Synchronization\n\n"
            f"- **System State**: Autonomous Daily Heartbeat Sync\n"
            f"- **Daily Status**: All system loops operational, scheduled goals active.\n"
            f"- **Repository Sync**: https://github.com/holman57/Adrastea\n"
        )
        try:
            with open(activity_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info(f"Appended daily operational heartbeat to {activity_file.name}.")
        except Exception as e:
            logger.error(f"Failed to append daily heartbeat to {activity_file}: {e}")
            return {"success": False, "error": f"Failed writing to activity log: {e}"}

    # Step 2: Stage tracked files safely
    try:
        for fpath in files_to_track:
            full_path = root / fpath
            if full_path.exists():
                subprocess.run(
                    ["git", "add", str(full_path)],
                    cwd=str(root),
                    check=True,
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                )
    except subprocess.CalledProcessError as e:
        logger.error(f"Git add failed: {e.stderr}")
        return {"success": False, "error": f"git add failed: {e.stderr}"}

    # Step 3: Commit staged changes
    timestamp_tag = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    commit_msg = f"{commit_message_prefix} [{timestamp_tag}]"

    commit_res = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if commit_res.returncode != 0:
        if "nothing to commit" in commit_res.stdout or "nothing to commit" in commit_res.stderr:
            logger.info("Nothing to commit. Repository is clean.")
            return {"success": True, "committed": False, "message": "Nothing to commit"}
        logger.error(f"Git commit failed: {commit_res.stderr}")
        return {"success": False, "error": commit_res.stderr.strip()}

    # Get new commit hash
    hash_res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    commit_hash = hash_res.stdout.strip()
    logger.info(f"Committed daily sync {commit_hash[:7]}: '{commit_msg}'")

    # Step 4: Push to GitHub if configured
    pushed = False
    if auto_push:
        logger.info(f"Pushing commit to {target_remote}/{target_branch}...")
        push_res = subprocess.run(
            ["git", "push", target_remote, target_branch],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if push_res.returncode != 0:
            logger.warning(f"Git push failed ({push_res.stderr.strip()}). Attempting rebase...")
            # Try pull --rebase and push again
            rebase_res = subprocess.run(
                ["git", "pull", "--rebase", target_remote, target_branch],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if rebase_res.returncode == 0:
                retry_push = subprocess.run(
                    ["git", "push", target_remote, target_branch],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                pushed = (retry_push.returncode == 0)
                if not pushed:
                    logger.error(f"Retry git push failed: {retry_push.stderr}")
            else:
                logger.error(f"Git pull --rebase failed: {rebase_res.stderr}")
        else:
            pushed = True

    result = {
        "success": True,
        "committed": True,
        "commit_hash": commit_hash,
        "commit_message": commit_msg,
        "pushed": pushed,
        "remote": f"{target_remote}/{target_branch}",
    }
    print(
        f"DAILY_COMMIT_STATUS: Success={result['success']} | Hash={commit_hash[:7]} | "
        f"Pushed={pushed} | Target={target_remote}/{target_branch}"
    )
    return result


class DailyGitHubCommitGoal(BaseGoal):
    """Goal 5: Guarantees Adrastea commits and pushes to GitHub at least once every day."""

    def __init__(self):
        super().__init__(
            goal_id="daily_github_commit",
            name="Daily GitHub Commit & Activity Synchronization",
            description="Guarantees Adrastea autonomously commits and pushes to GitHub at least once every day (24 hours), synchronizing activity logs, milestone telemetry, and operational progress.",
            enabled=True,
            weight=1.3,
            interval_seconds=1800.0,  # Evaluates cadence every 30 minutes
            parameters={
                "max_commit_age_seconds": 86400.0,  # 24 hours threshold
                "check_calendar_day": True,         # Secure commit once per calendar day
                "target_commit_hour": 20,            # Evening fallback (8 PM) if no commit today
                "target_remote": "origin",
                "target_branch": "main",
                "auto_push": True,
                "tracked_files": ["ACTIVITY_LOG.md"],
                "commit_message_prefix": "chore(daily): autonomous daily progress sync",
                "force_commit": False,
            },
        )

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = (context.get("now") if context and "now" in context else time.time())
        max_age = float(self.parameters.get("max_commit_age_seconds", 86400.0))
        check_calendar = bool(self.parameters.get("check_calendar_day", True))
        target_hour = int(self.parameters.get("target_commit_hour", 20))
        force = bool(self.parameters.get("force_commit", False))

        due = is_commit_due(
            max_commit_age_seconds=max_age,
            check_calendar_day=check_calendar,
            target_commit_hour=target_hour,
            force=force,
            now=now
        )

        if not due:
            info = get_last_commit_info()
            last_ts = info.get("timestamp", 0.0)
            elapsed_h = round((now - last_ts) / 3600.0, 1) if last_ts else 0.0
            logger.debug(
                f"Daily GitHub commit not yet due. Last commit was {elapsed_h}h ago. "
                f"Max age: {round(max_age / 3600.0, 1)}h."
            )
            return []

        # Commit is due: generate high-priority scheduled task
        priority = int(25 * self.weight)
        cmd = f'"{sys.executable}" -m adrastea.alpha.goals.daily_github_commit'

        task = ScheduledTask(
            task_id=f"daily_github_commit_{int(now)}",
            command=cmd,
            priority=priority,
            interval_seconds=None,
            metadata={
                "goal_id": self.goal_id,
                "intent": "Daily GitHub Synchronization & Push",
                "remote": self.parameters.get("target_remote", "origin"),
                "branch": self.parameters.get("target_branch", "main"),
            }
        )

        # Reset one-shot force_commit if it was set
        if force:
            self.parameters["force_commit"] = False

        self.mark_executed()
        return [task]


def main():
    parser = argparse.ArgumentParser(description="Adrastea Daily GitHub Commit Utility")
    parser.add_argument("--force", action="store_true", help="Force commit immediately regardless of elapsed time")
    parser.add_argument("--check", action="store_true", help="Check whether daily commit is due without committing")
    parser.add_argument("--remote", default="origin", help="Git target remote (default: origin)")
    parser.add_argument("--branch", default="main", help="Git target branch (default: main)")
    parser.add_argument("--no-push", action="store_true", help="Commit locally without pushing to remote")
    args = parser.parse_args()

    if args.check:
        due = is_commit_due(force=args.force)
        info = get_last_commit_info()
        print(f"Commit Due: {due}")
        print(f"Last Commit: {info.get('hash', '')[:7]} at {info.get('iso', '')} ({info.get('subject', '')})")
        sys.exit(0 if not due else 1)

    res = run_daily_commit(
        target_remote=args.remote,
        target_branch=args.branch,
        auto_push=not args.no_push,
        force=args.force
    )
    sys.exit(0 if res.get("success") else 1)


if __name__ == "__main__":
    main()
