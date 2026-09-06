import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional
from .config import config

logger = logging.getLogger("Adrastea.Directives")


class DirectiveWatcher:
    """Monitors for instructions from Luke via DIRECTIVES.txt or GitHub Issue comments."""

    def __init__(self, directives_file: Optional[Path] = None, issue_number: int = 1):
        self.directives_file = directives_file or (config.root_dir / "DIRECTIVES.txt")
        self.issue_number = issue_number
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

    def check_file_directive(self) -> Optional[str]:
        """Read any user directive from DIRECTIVES.txt."""
        if not self.directives_file.exists():
            return None

        try:
            with open(self.directives_file, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and not l.strip().startswith("#")]
            
            if lines:
                directive = " ".join(lines)
                logger.info(f"Detected directive from DIRECTIVES.txt: '{directive}'")
                # Clear the file back to header so it isn't repeatedly triggered
                self._reset_directives_file()
                return directive
        except Exception as e:
            logger.error(f"Error reading directives file: {e}")
        return None

    def check_github_issue_directive(self) -> Optional[str]:
        """Check for user replies or comments on GitHub Issue #1."""
        try:
            res = subprocess.run(
                ["gh", "issue", "view", str(self.issue_number), "--json", "comments"],
                cwd=str(config.root_dir),
                capture_output=True,
                text=True
            )
            if res.returncode != 0 or not res.stdout.strip():
                return None

            data = json.loads(res.stdout)
            comments = data.get("comments", [])
            if not comments:
                return None

            # Get latest comment
            latest = comments[-1]
            comment_id = latest.get("id")
            author = latest.get("author", {}).get("login", "")
            body = latest.get("body", "").strip()

            # Only accept comments from Luke (@holman57) that are new
            if comment_id != self.last_seen_comment_id and author.lower() in ("holman57", "lukeh"):
                # Avoid re-reading automated bot comments
                if "[Adrastea Autonomous" not in body:
                    self.last_seen_comment_id = comment_id
                    logger.info(f"Detected new directive from GitHub Issue #{self.issue_number} by @{author}: '{body}'")
                    return body
        except Exception as e:
            logger.debug(f"GitHub issue check failed: {e}")
        return None

    def check_directives(self) -> Optional[str]:
        """Check all input channels for user directions."""
        return self.check_file_directive() or self.check_github_issue_directive()
