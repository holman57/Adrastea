import json
import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import config

logger = logging.getLogger("Adrastea.Directives")

# Strict Security Enforcement: Only accept commands from Luke (@holman57)
AUTHORIZED_DIRECTIVE_AUTHOR = "holman57"


DEFAULT_TARGET_REPOSITORIES = [
    "holman57/Adrastea",
    "holman57/hardcode",
    "holman57/speech-flow",
    "holman57/market-research",
    "holman57/interpretive-interface",
    "holman57/distributed-content-management",
]


class Directive(str):
    """String subclass representing an authenticated user directive with rich metadata.
    Provides complete backward-compatibility with code expecting a simple string,
    while offering goal_id, issue_number, topic, author, and repository properties.
    """
    author: str
    source: str
    repo: str
    issue_number: Optional[int]
    goal_id: Optional[str]
    topic: Optional[str]
    raw_comment_id: Optional[str]

    def __new__(
        cls,
        text: str,
        author: str = AUTHORIZED_DIRECTIVE_AUTHOR,
        source: str = "file",
        repo: str = "holman57/Adrastea",
        issue_number: Optional[int] = None,
        goal_id: Optional[str] = None,
        topic: Optional[str] = None,
        raw_comment_id: Optional[str] = None,
    ):
        obj = str.__new__(cls, text)
        obj.text = text
        obj.author = author
        obj.source = source
        obj.repo = repo
        obj.issue_number = issue_number
        obj.goal_id = goal_id
        obj.topic = topic
        obj.raw_comment_id = raw_comment_id
        return obj

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "author": self.author,
            "source": self.source,
            "repo": self.repo,
            "issue_number": self.issue_number,
            "goal_id": self.goal_id,
            "topic": self.topic,
            "raw_comment_id": self.raw_comment_id,
        }


class DirectiveWatcher:
    """Monitors for instructions from Luke (@holman57) via DIRECTIVES.txt or dedicated GitHub Issues across all repositories.
    Enforces strict security filtering: ignores all comments from any other user.
    Routes directives to specific autonomous goals or question topics.
    """

    def __init__(
        self,
        directives_file: Optional[Path] = None,
        default_issue_number: Optional[int] = None,
        correspondence_manager: Optional[Any] = None,
        seen_comments_file: Optional[Path] = None,
        target_repos: Optional[List[str]] = None,
    ):
        self.directives_file = directives_file or (config.root_dir / "DIRECTIVES.txt")
        self.default_issue_number = default_issue_number

        if correspondence_manager is not None:
            self.correspondence_manager = correspondence_manager
            self.target_repos = target_repos if target_repos is not None else [getattr(correspondence_manager, "repo", "holman57/Adrastea")]
        else:
            from .notifications.issue_manager import IssueCorrespondenceManager
            self.correspondence_manager = IssueCorrespondenceManager(repo="holman57/Adrastea")
            self.target_repos = target_repos if target_repos is not None else getattr(
                config, "target_repositories", DEFAULT_TARGET_REPOSITORIES
            )

        self._managers: Dict[str, Any] = {
            getattr(self.correspondence_manager, "repo", "holman57/Adrastea"): self.correspondence_manager
        }
        self._pending_directives: List[Directive] = []
        self.seen_comments_file = seen_comments_file or (config.data_dir / "processed_directives.json")
        self.seen_comment_ids: Set[str] = set()
        self.last_seen_comment_id: Optional[str] = None
        self.last_github_check_time: float = 0.0
        self.base_loop_interval: float = getattr(config, "issue_loop_interval_seconds", 900.0)
        self._load_seen_comments()
        self._ensure_directives_file()

    def get_correspondence_manager(self, repo: str) -> Any:
        """Get or initialize IssueCorrespondenceManager for a specific repository."""
        if repo not in self._managers:
            from .notifications.issue_manager import IssueCorrespondenceManager
            self._managers[repo] = IssueCorrespondenceManager(repo=repo)
        return self._managers[repo]

    def get_adaptive_interval(self) -> float:
        """Calculates adaptive loop interval based on system load (CPU, RAM).
        Baseline: ~15 minutes (900s). Moderate load: 30 minutes (1800s). Heavy load: 60 minutes (3600s).
        """
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            if cpu >= 75.0 or ram >= 85.0:
                return 3600.0
            elif cpu >= 40.0 or ram >= 70.0:
                return 1800.0
        except Exception:
            pass
        return self.base_loop_interval

    def should_check_github(self) -> bool:
        """Check if adaptive timer has elapsed."""
        if self.last_github_check_time <= 0.0:
            return True
        interval = self.get_adaptive_interval()
        return (time.time() - self.last_github_check_time) >= interval

    def _load_seen_comments(self) -> None:
        """Load already processed comment IDs from disk to prevent duplicate responses across restarts."""
        if self.seen_comments_file.exists():
            try:
                with open(self.seen_comments_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.seen_comment_ids = set(data)
                    elif isinstance(data, dict):
                        self.seen_comment_ids = set(data.get("seen_comment_ids", []))
            except Exception as e:
                logger.debug(f"Failed to load processed comments: {e}")

    def _save_seen_comments(self) -> None:
        """Persist processed comment IDs to disk."""
        try:
            self.seen_comments_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.seen_comments_file, "w", encoding="utf-8") as f:
                json.dump({"seen_comment_ids": sorted(list(self.seen_comment_ids))}, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to save processed comments: {e}")

    def _ensure_directives_file(self) -> None:
        if not self.directives_file.exists():
            self._reset_directives_file()

    def _reset_directives_file(self) -> None:
        with open(self.directives_file, "w", encoding="utf-8") as f:
            f.write(
                "# Type any directions, goals, or tasks for Adrastea below and save this file.\n"
                "# Adrastea will detect it, execute it, and report back.\n"
            )

    def check_file_directive(self) -> Optional[Directive]:
        """Read any user directive from DIRECTIVES.txt."""
        if not self.directives_file.exists():
            return None

        try:
            with open(self.directives_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]

            if lines:
                directive_text = " ".join(lines)
                logger.info(f"Detected directive from DIRECTIVES.txt: '{directive_text}'")
                self._reset_directives_file()
                return Directive(
                    text=directive_text,
                    author=AUTHORIZED_DIRECTIVE_AUTHOR,
                    source="file",
                    goal_id=None,
                    issue_number=None,
                    topic="Local Directive File",
                )
        except Exception as e:
            logger.error(f"Error reading directives file: {e}")
        return None

    def _get_monitored_issue_numbers(self, mgr: Optional[Any] = None) -> List[int]:
        """Get list of active issues to inspect for directives for a given manager."""
        mgr = mgr or self.correspondence_manager
        issues: List[int] = []
        if getattr(mgr, "repo", "") == "holman57/Adrastea" and self.default_issue_number is not None:
            issues.append(self.default_issue_number)

        try:
            open_issues = mgr.list_open_issues()
            for item in open_issues:
                num = int(item["number"])
                if num not in issues:
                    issues.append(num)
        except Exception as e:
            logger.debug(f"Failed to list monitored issues for {getattr(mgr, 'repo', 'default')}: {e}")

        # Fallback to local registry if GitHub list is empty or fails
        if not issues and hasattr(mgr, "registry"):
            reg = mgr.registry.get("issue_to_target", {})
            for num_str in reg.keys():
                num = int(num_str)
                if num not in issues:
                    issues.append(num)

        return issues

    def check_github_issue_directive(self, force: bool = True) -> Optional[Directive]:
        """Check for user replies or comments on GitHub issues across all target repositories.
        - Ignores deleted/inaccessible issues.
        - Respects escalating backoff for waiting issues ("unless it has been days").
        - Inspects issues created directly by @holman57 as potential directives.
        - Strictly enforces that ONLY @holman57 can trigger system actions.
        - Responds with friendly pleasantries to external contributors without executing actions.
        - Buffers multiple detected directives to process smoothly across cognitive ticks.
        """
        if self._pending_directives:
            return self._pending_directives.pop(0)

        for repo in self.target_repos:
            mgr = self.get_correspondence_manager(repo)
            issues_to_check = self._get_monitored_issue_numbers(mgr)

            for issue_num in issues_to_check:
                try:
                    # 1. Safely retrieve issue details and comments (handles deleted issues)
                    issue_data = None
                    if hasattr(mgr, "get_issue_data"):
                        issue_data = mgr.get_issue_data(issue_num)

                    if issue_data is not None:
                        comments = issue_data.get("comments", [])
                        issue_title = issue_data.get("title", "")
                        issue_body = issue_data.get("body", "")
                        issue_author = issue_data.get("author", {}).get("login", "").strip().lower()
                    else:
                        comments = mgr.get_issue_comments(issue_num)
                        issue_title = ""
                        issue_body = ""
                        issue_author = ""

                    # Ignore deleted or inaccessible issues
                    if issue_data is None and not comments:
                        if hasattr(mgr, "_is_issue_open") and not mgr._is_issue_open(issue_num):
                            logger.debug(f"Issue #{issue_num} on {repo} is closed or deleted. Skipping.")
                            continue

                    target_info = (
                        mgr.get_target_for_issue(issue_num)
                        if hasattr(mgr, "get_target_for_issue")
                        else None
                    )
                    is_registered_target = bool(target_info and target_info.get("type") in ("goal", "question"))

                    # Scoped IDs to prevent cross-repo collisions
                    scoped_body_id = f"{repo}:issue_body_{issue_num}"
                    is_body_seen = (
                        scoped_body_id in self.seen_comment_ids
                        or (repo == "holman57/Adrastea" and f"issue_body_{issue_num}" in self.seen_comment_ids)
                    )

                    # 2. Check if the issue was created by Luke (@holman57) or external user
                    if issue_author == AUTHORIZED_DIRECTIVE_AUTHOR.lower() and not is_body_seen:
                        is_adrastea_issue = (
                            is_registered_target
                            or (
                                mgr.is_adrastea_content(issue_body, issue_author)
                                if hasattr(mgr, "is_adrastea_content")
                                else ("[Adrastea" in issue_body or "**Autonomous" in issue_body or "Generated automatically by" in issue_body)
                            )
                        )
                        if not is_adrastea_issue:
                            # Genuine issue created by Luke (@holman57)
                            has_adrastea_reply = any(
                                (
                                    mgr.is_adrastea_content(c.get("body", ""), c.get("author", {}).get("login", ""))
                                    if hasattr(mgr, "is_adrastea_content")
                                    else ("[Adrastea" in c.get("body", ""))
                                )
                                for c in comments
                            )
                            if has_adrastea_reply:
                                self.seen_comment_ids.add(scoped_body_id)
                                if repo == "holman57/Adrastea":
                                    self.seen_comment_ids.add(f"issue_body_{issue_num}")
                                self._save_seen_comments()
                            else:
                                raw_body_id = f"issue_body_{issue_num}" if repo == "holman57/Adrastea" else scoped_body_id
                                self.seen_comment_ids.add(scoped_body_id)
                                self.seen_comment_ids.add(raw_body_id)
                                self.last_seen_comment_id = raw_body_id
                                self._save_seen_comments()
                                if hasattr(mgr, "reset_issue_wait"):
                                    mgr.reset_issue_wait(issue_num)

                                directive_text = f"{issue_title}\n\n{issue_body}".strip() if issue_body else issue_title
                                goal_id = (
                                    target_info.get("id")
                                    if target_info and target_info.get("type") == "goal"
                                    else ("companion_feature_builder" if repo != "holman57/Adrastea" else None)
                                )
                                repo_short = repo.split("/")[-1]
                                topic = (
                                    target_info.get("title")
                                    if target_info
                                    else (
                                        f"[{repo_short}] {issue_title or f'Issue #{issue_num}'}"
                                        if repo != "holman57/Adrastea"
                                        else (issue_title or f"Issue #{issue_num}")
                                    )
                                )

                                logger.info(
                                    f"Security Verified: Directive received from newly created Issue #{issue_num} on {repo} "
                                    f"by @{issue_author}: '{directive_text}'"
                                )
                                d = Directive(
                                    text=directive_text,
                                    author=issue_author,
                                    source="github_issue",
                                    repo=repo,
                                    issue_number=issue_num,
                                    goal_id=goal_id,
                                    topic=topic,
                                    raw_comment_id=raw_body_id,
                                )
                                self._pending_directives.append(d)
                        else:
                            self.seen_comment_ids.add(scoped_body_id)
                            self._save_seen_comments()
                    elif issue_author and issue_author != AUTHORIZED_DIRECTIVE_AUTHOR.lower() and not is_body_seen:
                        # External contributor opened an issue: send pleasantry
                        self.seen_comment_ids.add(scoped_body_id)
                        self._save_seen_comments()
                        if hasattr(mgr, "post_contributor_pleasantry"):
                            logger.info(f"Issue #{issue_num} on {repo} created by external user @{issue_author}. Responding with pleasantry.")
                            mgr.post_contributor_pleasantry(issue_num, issue_author)

                    # 3. Check if issue is waiting on operator response with escalating backoff
                    waiting, reason = mgr.is_waiting_for_user_response(issue_num, issue_data=issue_data)
                    if waiting:
                        # Suppress re-reading older comments on waiting threads
                        for c in comments:
                            cid = c.get("id")
                            if cid:
                                scoped_cid = f"{repo}:{cid}"
                                if scoped_cid not in self.seen_comment_ids:
                                    self.seen_comment_ids.add(scoped_cid)
                        self._save_seen_comments()
                        continue

                    # 4. Check if escalating wait period expired ("unless it has been days")
                    if "safe to send status follow-up" in reason.lower() or "expired" in reason.lower():
                        wait_count = (
                            mgr.get_wait_count(issue_num)
                            if hasattr(mgr, "get_wait_count")
                            else 0
                        )
                        follow_up = (
                            f"### [Adrastea Autonomous Status & Inquiries]\n\n"
                            f"Periodic follow-up on this thread for @{AUTHORIZED_DIRECTIVE_AUTHOR}: "
                            f"Adrastea is standing by for any steering, priorities, or feedback on this topic.\n\n"
                            f"- **Follow-up Index:** #{wait_count + 1}\n"
                            f"- **Escalating Backoff:** Next wait window will escalate automatically to avoid thread clutter."
                        )
                        mgr.post_response_to_issue(issue_num, follow_up, force=True)
                        continue

                    if not comments:
                        continue

                    for idx, comment in enumerate(comments):
                        comment_id = comment.get("id")
                        author = comment.get("author", {}).get("login", "").strip().lower()
                        body = comment.get("body", "").strip()

                        if not comment_id:
                            continue

                        scoped_comment_id = f"{repo}:{comment_id}"
                        is_comment_seen = (
                            scoped_comment_id in self.seen_comment_ids
                            or (repo == "holman57/Adrastea" and comment_id in self.seen_comment_ids)
                        )
                        if is_comment_seen:
                            continue

                        # Ignore bot/autonomous comments
                        is_adrastea_comment = (
                            mgr.is_adrastea_content(body, author)
                            if hasattr(mgr, "is_adrastea_content")
                            else (
                                "[Adrastea Autonomous" in body
                                or "### [Adrastea" in body
                                or "ADRASTEA AUTONOMOUS SYSTEM REPORT" in body
                                or "Generated automatically by" in body
                                or "Growth & Star Acceleration Blueprint" in body
                                or "Adrastea GitHub Profile" in body
                                or author in ("github-actions[bot]", "holman57[bot]")
                            )
                        )
                        if is_adrastea_comment:
                            self.seen_comment_ids.add(scoped_comment_id)
                            self._save_seen_comments()
                            continue

                        # STRICT SECURITY: Only accept comments from AUTHORIZED_DIRECTIVE_AUTHOR (holman57)
                        if author != AUTHORIZED_DIRECTIVE_AUTHOR.lower():
                            self.seen_comment_ids.add(scoped_comment_id)
                            self._save_seen_comments()
                            logger.warning(
                                f"Security: Ignored directive on Issue #{issue_num} ({repo}) from unauthorized user '@{author}'. "
                                f"Only @{AUTHORIZED_DIRECTIVE_AUTHOR} is permitted to give instructions. Sending pleasantry."
                            )
                            if hasattr(mgr, "post_contributor_pleasantry"):
                                mgr.post_contributor_pleasantry(issue_num, author)
                            continue

                        # Check if any subsequent comment is already an Adrastea reply for this directive
                        has_subsequent_adrastea_reply = any(
                            (
                                mgr.is_adrastea_content(nc.get("body", ""), nc.get("author", {}).get("login", ""))
                                if hasattr(mgr, "is_adrastea_content")
                                else ("[Adrastea" in nc.get("body", ""))
                            )
                            for nc in comments[idx + 1:]
                        )
                        if has_subsequent_adrastea_reply:
                            self.seen_comment_ids.add(scoped_comment_id)
                            self._save_seen_comments()
                            continue

                        raw_cid = comment_id if repo == "holman57/Adrastea" else scoped_comment_id
                        self.seen_comment_ids.add(scoped_comment_id)
                        self.seen_comment_ids.add(raw_cid)
                        self.last_seen_comment_id = raw_cid
                        self._save_seen_comments()
                        if hasattr(mgr, "reset_issue_wait"):
                            mgr.reset_issue_wait(issue_num)

                        # Target goal or question lookup
                        target_info = mgr.get_target_for_issue(issue_num)
                        goal_id = (
                            target_info.get("id")
                            if target_info and target_info.get("type") == "goal"
                            else ("companion_feature_builder" if repo != "holman57/Adrastea" else None)
                        )
                        repo_short = repo.split("/")[-1]
                        topic = (
                            target_info.get("title")
                            if target_info
                            else (
                                f"[{repo_short}] {issue_title or f'Issue #{issue_num}'}"
                                if repo != "holman57/Adrastea"
                                else (issue_title or f"Issue #{issue_num}")
                            )
                        )

                        logger.info(
                            f"Security Verified: Directive received on Issue #{issue_num} ({repo}, Goal: {goal_id}) "
                            f"by @{author}: '{body}'"
                        )
                        d = Directive(
                            text=body,
                            author=author,
                            source="github_issue",
                            repo=repo,
                            issue_number=issue_num,
                            goal_id=goal_id,
                            topic=topic,
                            raw_comment_id=raw_cid,
                        )
                        self._pending_directives.append(d)

                except Exception as e:
                    logger.debug(f"GitHub issue check failed for issue #{issue_num} on {repo}: {e}")

        if self._pending_directives:
            return self._pending_directives.pop(0)

        return None

    def check_directives(self, force: bool = False) -> Optional[Directive]:
        """Check all input channels for user directions.
        Local DIRECTIVES.txt is checked on every invocation.
        Buffered pending directives are drained immediately on each cycle.
        GitHub issue loop runs on an adaptive cadence (~15m or longer under heavy load) unless forced.
        """
        file_directive = self.check_file_directive()
        if file_directive:
            return file_directive

        if self._pending_directives:
            return self._pending_directives.pop(0)

        if force or self.should_check_github():
            self.last_github_check_time = time.time()
            return self.check_github_issue_directive(force=force)

        return None
