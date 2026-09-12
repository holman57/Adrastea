"""
Tests for in-place comment editing, single-reply turn-based commenting,
summarization, and comment noise elimination across repositories.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from adrastea.notifications.issue_manager import (
    AUTHORIZED_OPERATOR,
    IssueCorrespondenceManager,
    cleanup_all_repos_comment_noise,
)


class TestIssueCommentEditing(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_file = Path(self.temp_dir.name) / "issue_registry.json"
        self.mgr = IssueCorrespondenceManager(repo="holman57/Adrastea", registry_file=self.registry_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=True)
    @patch.object(IssueCorrespondenceManager, "delete_issue_comment", return_value=True)
    @patch("subprocess.run")
    def test_post_response_edits_existing_comment_in_place(
        self, mock_subproc, mock_delete, mock_edit, mock_get_comments
    ):
        """When an Adrastea reply already exists in the current turn, Adrastea must edit it in-place,
        not create a new comment.
        """
        mock_get_comments.return_value = [
            {
                "id": 101,
                "author": {"login": "holman57"},
                "body": "Please add feature X to the repository.",
            },
            {
                "id": 201,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Status & Response]\n\nInitial acknowledgment.",
            },
        ]

        res = self.mgr.post_response_to_issue(
            issue_number=1,
            response_markdown="Updated roadmap: Step 1 completed, Step 2 in progress.",
            force=True,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "edited")
        self.assertEqual(res["comment_id"], 201)

        # Must have called edit_issue_comment on existing comment #201
        mock_edit.assert_called_once()
        args, _ = mock_edit.call_args
        self.assertEqual(args[0], 201)
        self.assertIn("Updated roadmap", args[1])

        # Must NOT have run 'gh issue comment' to create a new comment
        self.assertFalse(mock_subproc.called)

    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=True)
    @patch("subprocess.run")
    def test_post_response_creates_new_comment_after_operator_reply(
        self, mock_subproc, mock_edit, mock_get_comments
    ):
        """When Luke (@holman57) comments and Adrastea has not replied to this new turn yet,
        Adrastea must create a single new comment.
        """
        mock_get_comments.return_value = [
            {
                "id": 101,
                "author": {"login": "holman57"},
                "body": "First directive.",
            },
            {
                "id": 201,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Status & Response]\n\nFirst reply.",
            },
            {
                "id": 102,
                "author": {"login": "holman57"},
                "body": "New directive: Change architecture to use SQLite.",
            },
        ]

        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout="https://github.com/holman57/Adrastea/issues/1#issuecomment-301",
        )

        res = self.mgr.post_response_to_issue(
            issue_number=1,
            response_markdown="Adopted SQLite architecture decision.",
            force=True,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["action"], "created")

        # Must NOT have edited old comment #201
        self.assertFalse(mock_edit.called)

        # Must have created a new comment via gh CLI
        mock_subproc.assert_called_once()
        cmd = mock_subproc.call_args[0][0]
        self.assertEqual(cmd[:3], ["gh", "issue", "comment"])

    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=True)
    @patch.object(IssueCorrespondenceManager, "delete_issue_comment", return_value=True)
    def test_subsequent_updates_edit_same_comment(
        self, mock_delete, mock_edit, mock_get_comments
    ):
        """Consecutive autonomous updates in the same turn continuously edit the same reply comment."""
        mock_get_comments.return_value = [
            {
                "id": 500,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Status & Response]\n\nLoop 1 status.",
            }
        ]

        # Update 1
        res1 = self.mgr.post_response_to_issue(issue_number=2, response_markdown="Loop 2 update", force=True)
        self.assertEqual(res1["action"], "edited")
        self.assertEqual(res1["comment_id"], 500)

        # Update 2
        res2 = self.mgr.post_response_to_issue(issue_number=2, response_markdown="Loop 3 update", force=True)
        self.assertEqual(res2["action"], "edited")
        self.assertEqual(res2["comment_id"], 500)

        self.assertEqual(mock_edit.call_count, 2)

    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=True)
    @patch.object(IssueCorrespondenceManager, "delete_issue_comment", return_value=True)
    def test_duplicate_noise_comments_deleted_on_update(
        self, mock_delete, mock_edit, mock_get_comments
    ):
        """When an issue contains multiple Adrastea comments in a turn, posting updates edits the primary
        and deletes the extra duplicate comments.
        """
        mock_get_comments.return_value = [
            {
                "id": 101,
                "author": {"login": "holman57"},
                "body": "Directive",
            },
            {
                "id": 201,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update] Msg 1",
            },
            {
                "id": 202,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update] Msg 2",
            },
            {
                "id": 203,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update] Msg 3",
            },
        ]

        res = self.mgr.post_response_to_issue(
            issue_number=1,
            response_markdown="Consolidated state",
            force=True,
        )

        self.assertEqual(res["action"], "edited")
        self.assertEqual(res["comment_id"], 201)

        # Primary comment 201 was edited
        mock_edit.assert_called_once()
        self.assertEqual(mock_edit.call_args[0][0], 201)

        # Extra noise comments 202 and 203 were deleted
        self.assertEqual(mock_delete.call_count, 2)
        deleted_ids = [c[0][0] for c in mock_delete.call_args_list]
        self.assertEqual(deleted_ids, [202, 203])

    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=True)
    @patch.object(IssueCorrespondenceManager, "delete_issue_comment", return_value=True)
    def test_summarize_and_consolidate_issue_comments(
        self, mock_delete, mock_edit, mock_get_comments
    ):
        """Test full comment consolidation: multiple noisy Adrastea comments are summarized into
        the primary reply, extras deleted, and operator comments preserved untouched.
        """
        mock_get_comments.return_value = [
            # Turn 0: Adrastea initial status
            {
                "id": 1,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Status & Response]\n\nInitial status.",
            },
            {
                "id": 2,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update]\n\nDuplicate ping.",
            },
            # Turn 1: Luke comments
            {
                "id": 10,
                "author": {"login": "holman57"},
                "body": "Let's focus on benchmarking the scheduler.",
            },
            # Turn 1: Adrastea noise comments
            {
                "id": 20,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Guidance Adopted via Gemini]\n\n**Architectural Decision:** Prioritize benchmarking.\n#### **Step 1: Benchmark suite**",
            },
            {
                "id": 21,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update]\n\nDuplicate autonomous tick.",
            },
            {
                "id": 22,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Update]\n\nAnother duplicate tick.",
            },
        ]

        res = self.mgr.summarize_and_consolidate_issue_comments(issue_number=5)
        self.assertTrue(res["success"])
        self.assertEqual(res["total_comments_before"], 6)
        self.assertEqual(res["edited"], 2)  # Comment #1 in Turn 0, Comment #20 in Turn 1
        self.assertEqual(res["deleted"], 3)  # Comment #2 in Turn 0, Comments #21 and #22 in Turn 1
        self.assertEqual(res["remaining_comments"], 3)

        # Comment #10 from Luke (@holman57) was NOT deleted
        deleted_ids = [c[0][0] for c in mock_delete.call_args_list]
        self.assertNotIn(10, deleted_ids)
        self.assertEqual(deleted_ids, [2, 21, 22])

        # Verify edited content has summary structure
        edited_calls = mock_edit.call_args_list
        turn1_summary = edited_calls[1][0][1]
        self.assertIn("Architectural Strategy & Decisions", turn1_summary)
        self.assertIn("Prioritize benchmarking", turn1_summary)

    @patch("subprocess.run")
    def test_cleanup_all_repos_deletes_growth_issues_outside_adrastea(self, mock_subproc):
        """Verify cleanup_all_repos_comment_noise deletes [Growth Strategy] issues on companion repos."""
        def fake_run(cmd, *args, **kwargs):
            cmd_str = " ".join(cmd)
            # List issues on hardcode
            if "gh issue list --repo holman57/hardcode --state all" in cmd_str:
                return MagicMock(returncode=0, stdout=json.dumps([
                    {"number": 15, "title": "[Growth Strategy] Accelerating holman57 Profile & Repository Engagement"},
                    {"number": 9, "title": "Regular issue"},
                ]))
            # List issues on other repos
            if "gh issue list --repo" in cmd_str and "--state all" in cmd_str:
                return MagicMock(returncode=0, stdout="[]")
            if "gh issue list --repo" in cmd_str and "--state open" in cmd_str:
                return MagicMock(returncode=0, stdout="[]")
            # Delete issue
            if "gh issue delete 15 --repo holman57/hardcode --yes" in cmd_str:
                return MagicMock(returncode=0, stdout="")
            return MagicMock(returncode=0, stdout="[]")

        mock_subproc.side_effect = fake_run
        res = cleanup_all_repos_comment_noise()

        deleted = res["deleted_issues"]
        self.assertEqual(len(deleted), 1)
        self.assertEqual(deleted[0]["repo"], "holman57/hardcode")
        self.assertEqual(deleted[0]["issue_number"], 15)

    @patch("subprocess.run")
    @patch.object(IssueCorrespondenceManager, "get_paginated_issue_comments")
    @patch.object(IssueCorrespondenceManager, "edit_issue_comment", return_value=False)
    def test_edit_failure_does_not_fallback_to_creation(
        self, mock_edit, mock_get_comments, mock_subproc
    ):
        """When an Adrastea comment exists but edit_issue_comment fails, Adrastea must NEVER
        fall back to creating a new comment, preserving the single-reply rule.
        """
        mock_get_comments.return_value = [
            {
                "id": 888,
                "author": {"login": "github-actions[bot]"},
                "body": "### [Adrastea Autonomous Status & Response]\n\nExisting comment.",
            }
        ]
        res = self.mgr.post_response_to_issue(
            issue_number=2,
            response_markdown="Attempted follow up",
            force=True,
        )
        self.assertFalse(res["success"])
        self.assertEqual(res["action"], "edit_failed")
        # Subprocess (gh issue comment) must NOT have been called!
        mock_subproc.assert_not_called()


if __name__ == "__main__":
    unittest.main()

