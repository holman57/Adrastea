import json
import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import config

logger = logging.getLogger("Adrastea.Directives")

# Strict Security Enforcement: Only accept commands from Luke (@holman57)
AUTHORIZED_DIRECTIVE_AUTHOR = "holman57"


class Directive(str):
    """String subclass representing an authenticated user directive with rich metadata.
    Provides complete backward-compatibility with code expecting a simple string,
    while offering goal_id, issue_number, topic, and author properties.
    """
    author: str
    source: str
    issue_number: Optional[int]
    goal_id: Optional[str]
    topic: Optional[str]
    raw_comment_id: Optional[str]

    def __new__(
        cls,
        text: str,
        author: str = AUTHORIZED_DIRECTIVE_AUTHOR,
        source: str = "file",
        issue_number: Optional[int] = None,
        goal_id: Optional[str] = None,
        topic: Optional[str] = None,
        raw_comment_id: Optional[str] = None,
    ):
        obj = str.__new__(cls, text)
        obj.text = text
        obj.author = author
        obj.source = source
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
            "issue_number": self.issue_number,
            "goal_id": self.goal_id,
            "topic": self.topic,
            "raw_comment_id": self.raw_comment_id,
        }


class DirectiveWatcher:
    """Monitors for instructions from Luke (@holman57) via DIRECTIVES.txt or dedicated GitHub Issues.
    Enforces strict security filtering: ignores all comments from any other user.
    Routes directives to specific autonomous goals or question topics.
    """

    def __init__(
        self,
        directives_file: Optional[Path] = None,
        default_issue_number: Optional[int] = None,
        correspondence_manager: Optional[Any] = None,
    ):
        self.directives_file = directives_file or (config.root_dir / "DIRECTIVES.txt")
        self.default_issue_number = default_issue_number

        if correspondence_manager is not None:
            self.correspondence_manager = correspondence_manager
        else:
            from .notifications.issue_manager import IssueCorrespondenceManager
            self.correspondence_manager = IssueCorrespondenceManager()

        self.seen_comment_ids: Set[str] = set()
        self.last_seen_comment_id: Optional[str] = None
        self._ensure_directives_file()

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

    def _get_monitored_issue_numbers(self) -> List[int]:
        """Get list of active issues to inspect for directives."""
        issues: List[int] = []
        if self.default_issue_number is not None:
            issues.append(self.default_issue_number)

        try:
            open_issues = self.correspondence_manager.list_open_issues()
            for item in open_issues:
                num = int(item["number"])
                if num not in issues:
                    issues.append(num)
        except Exception as e:
            logger.debug(f"Failed to list monitored issues: {e}")

        # Fallback to local registry if GitHub list is empty or fails
        if not issues and hasattr(self.correspondence_manager, "registry"):
            reg = self.correspondence_manager.registry.get("issue_to_target", {})
            for num_str in reg.keys():
                num = int(num_str)
                if num not in issues:
                    issues.append(num)

        return issues

    def check_github_issue_directive(self) -> Optional[Directive]:
        """Check for user replies or comments on GitHub issues.
        Strictly enforces that ONLY comments from @holman57 are accepted.
        Resolves the corresponding goal or question topic for the issue.
        """
        issues_to_check = self._get_monitored_issue_numbers()

        for issue_num in issues_to_check:
            try:
                comments = self.correspondence_manager.get_issue_comments(issue_num)
                if not comments:
                    continue

                for comment in comments:
                    comment_id = comment.get("id")
                    author = comment.get("author", {}).get("login", "").strip().lower()
                    body = comment.get("body", "").strip()

                    # Check if already processed
                    if comment_id in self.seen_comment_ids:
                        continue

                    self.seen_comment_ids.add(comment_id)
                    self.last_seen_comment_id = comment_id

                    # Ignore bot/autonomous comments
                    if (
                        "[Adrastea Autonomous" in body
                        or "### [Adrastea" in body
                        or "ADRASTEA AUTONOMOUS SYSTEM REPORT" in body
                        or author in ("github-actions[bot]", "holman57[bot]")
                    ):
                        continue

                    # STRICT SECURITY: Only accept comments from AUTHORIZED_DIRECTIVE_AUTHOR (holman57)
                    if author != AUTHORIZED_DIRECTIVE_AUTHOR:
                        logger.warning(
                            f"Security: Ignored comment {comment_id} on issue #{issue_num} from unauthorized user '@{author}'. "
                            f"Only @{AUTHORIZED_DIRECTIVE_AUTHOR} is permitted to give instructions."
                        )
                        continue

                    # Target goal or question lookup
                    target_info = self.correspondence_manager.get_target_for_issue(issue_num)
                    goal_id = target_info.get("id") if target_info and target_info.get("type") == "goal" else None
                    topic = target_info.get("title") if target_info else f"Issue #{issue_num}"

                    logger.info(
                        f"Security Verified: Directive received on Issue #{issue_num} (Goal: {goal_id}) "
                        f"by @{author}: '{body}'"
                    )
                    return Directive(
                        text=body,
                        author=author,
                        source="github_issue",
                        issue_number=issue_num,
                        goal_id=goal_id,
                        topic=topic,
                        raw_comment_id=comment_id,
                    )

            except Exception as e:
                logger.debug(f"GitHub issue check failed for issue #{issue_num}: {e}")

        return None

    def check_directives(self) -> Optional[Directive]:
        """Check all input channels for user directions."""
        return self.check_file_directive() or self.check_github_issue_directive()
