import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adrastea.directives import AUTHORIZED_DIRECTIVE_AUTHOR, Directive, DirectiveWatcher
from adrastea.notifications.issue_manager import (
    GOAL_DEFINITIONS,
    QUESTION_DEFINITIONS,
    GitHubTopicManager,
    IssueCorrespondenceManager,
)


class TestIssueManagerAndSecurity(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.directives_file = Path(self.temp_dir.name) / "DIRECTIVES.txt"
        self.registry_file = Path(self.temp_dir.name) / "issue_registry.json"
        self.seen_comments_file = Path(self.temp_dir.name) / "processed_directives.json"
        self.topic_mgr = IssueCorrespondenceManager(repo="holman57/Adrastea", registry_file=self.registry_file)
        self.watcher = DirectiveWatcher(
            directives_file=self.directives_file,
            correspondence_manager=self.topic_mgr,
            seen_comments_file=self.seen_comments_file,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("subprocess.run")
    def test_security_authorization_only_holman57(self, mock_subproc):
        # Case 1: Comment from unauthorized user "random_attacker"
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c1", "author": {"login": "random_attacker"}, "body": "rm -rf /"}
                ]
            }'''
        )
        directive = self.watcher.check_github_issue_directive()
        # MUST BE IGNORED
        self.assertIsNone(directive)

        # Case 2: Comment from Luke (@holman57) on Issue #4 (Ecosystem repos)
        self.topic_mgr.registry["issue_to_target"]["4"] = {
            "type": "goal",
            "id": "ecosystem_repos",
            "title": "[Goal] Companion AI-Managed Projects"
        }
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c2", "author": {"login": "holman57"}, "body": "Focus on speech-flow"}
                ]
            }'''
        )
        # Mock _get_monitored_issue_numbers to return [4]
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[4]):
            directive_luke = self.watcher.check_github_issue_directive()

        # MUST BE ACCEPTED and properly mapped
        self.assertIsNotNone(directive_luke)
        self.assertEqual(directive_luke, "Focus on speech-flow")
        self.assertEqual(directive_luke.author, "holman57")
        self.assertEqual(directive_luke.source, "github_issue")
        self.assertEqual(directive_luke.issue_number, 4)
        self.assertEqual(directive_luke.goal_id, "ecosystem_repos")

    @patch("subprocess.run")
    def test_anti_spam_wait_for_user_response(self, mock_subproc):
        # Case 1: Issue has an unanswered autonomous update
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c10", "author": {"login": "holman57"}, "body": "Initial directive"},
                    {"id": "c11", "author": {"login": "github-actions[bot]"}, "body": "### [Adrastea Autonomous Update] System status..."}
                ]
            }'''
        )
        waiting, reason = self.topic_mgr.is_waiting_for_user_response(issue_number=1)
        # Should be TRUE (must wait for Luke to reply before posting again)
        self.assertTrue(waiting)
        self.assertIn("already waiting on a response", reason)

        # Suppresses posting when waiting
        res = self.topic_mgr.post_response_to_issue(1, "Another update")
        self.assertFalse(res["success"])
        self.assertTrue(res.get("suppressed"))

        # Case 2: Luke (@holman57) replied to the autonomous update
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c11", "author": {"login": "github-actions[bot]"}, "body": "### [Adrastea Autonomous Update] System status..."},
                    {"id": "c12", "author": {"login": "holman57"}, "body": "Great, proceed with the tests."}
                ]
            }'''
        )
        waiting_after_reply, reason_reply = self.topic_mgr.is_waiting_for_user_response(issue_number=1)
        # Should be FALSE (safe to respond because Luke replied!)
        self.assertFalse(waiting_after_reply)
        self.assertIn("safe to respond", reason_reply)

    @patch("subprocess.run")
    def test_topic_issue_localization(self, mock_subproc):
        # Test finding existing issue matching topic words
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''[
                {"number": 42, "title": "[Topic] Speech-Flow Voice Interface Architecture", "labels": []}
            ]'''
        )
        issue_num = self.topic_mgr.find_topic_issue("Speech-Flow Voice Interface")
        self.assertEqual(issue_num, 42)

    def test_file_directive_returns_rich_directive(self):
        with open(self.directives_file, "w", encoding="utf-8") as f:
            f.write("Optimize memory consolidation decay\n")

        d = self.watcher.check_file_directive()
        self.assertIsNotNone(d)
        self.assertEqual(d, "Optimize memory consolidation decay")
        self.assertEqual(d.source, "file")
        self.assertEqual(d.author, "holman57")
        self.assertIsNone(d.goal_id)

    @patch("subprocess.run")
    def test_ensure_all_issues_sync(self, mock_subproc):
        # Mock listing open issues on GitHub
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {"number": 2, "title": "[Goal] Adrastea Self-Evolution & Repository Growth", "labels": []},
                {"number": 3, "title": "[Goal] User Coordination & Strategic Steering", "labels": []},
                {"number": 4, "title": "[Goal] Companion AI-Managed Projects (speech-flow, interpretive-interface, distributed-content-management)", "labels": []},
                {"number": 5, "title": "[Goal] Graph Knowledge Base & Multi-Tier Memory System (Neo4j / SQLite)", "labels": []},
                {"number": 6, "title": "[Question] Audio Output Policy & Speech-Flow Voice Bridge Configuration", "labels": []},
                {"number": 7, "title": "[Question] Neo4j Connection & External Graph Synchronization Parameters", "labels": []},
            ])
        )

        reg = self.topic_mgr.sync_registry()
        self.assertEqual(self.topic_mgr.get_issue_for_goal("adrastea_self_evolution"), 2)
        self.assertEqual(self.topic_mgr.get_issue_for_goal("user_coordination"), 3)
        self.assertEqual(self.topic_mgr.get_issue_for_goal("ecosystem_repos"), 4)
        self.assertEqual(self.topic_mgr.get_issue_for_goal("knowledge_graph_memory"), 5)

        target = self.topic_mgr.get_target_for_issue(4)
        self.assertIsNotNone(target)
        self.assertEqual(target["id"], "ecosystem_repos")
        self.assertEqual(target["type"], "goal")

    @patch("subprocess.run")
    def test_persistent_seen_comments_prevents_duplicate_processing(self, mock_subproc):
        # Comments list where Luke responded
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c_unique_101", "author": {"login": "holman57"}, "body": "Do something new"}
                ]
            }'''
        )
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[4]):
            d1 = self.watcher.check_github_issue_directive()
            self.assertIsNotNone(d1)
            self.assertEqual(d1, "Do something new")

            # Second check with same comment: must be suppressed (None)
            d2 = self.watcher.check_github_issue_directive()
            self.assertIsNone(d2)

        # Re-instantiate watcher pointing to same seen_comments_file: must still be suppressed
        watcher_restart = DirectiveWatcher(
            directives_file=self.directives_file,
            correspondence_manager=self.topic_mgr,
            seen_comments_file=self.watcher.seen_comments_file
        )
        with patch.object(watcher_restart, "_get_monitored_issue_numbers", return_value=[4]):
            d_restarted = watcher_restart.check_github_issue_directive()
            self.assertIsNone(d_restarted)

    @patch("subprocess.run")
    def test_subsequent_adrastea_reply_suppresses_old_directive(self, mock_subproc):
        # Issue where Luke posted a directive, but Adrastea already replied later in the thread
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout='''{
                "comments": [
                    {"id": "c_old_1", "author": {"login": "holman57"}, "body": "Old instruction"},
                    {"id": "c_reply_1", "author": {"login": "holman57"}, "body": "### [Adrastea Autonomous Update] Adopted directive..."},
                    {"id": "c_new_2", "author": {"login": "holman57"}, "body": "Fresh instruction"}
                ]
            }'''
        )
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[4]):
            d = self.watcher.check_github_issue_directive()
            # Must return the NEW instruction (c_new_2), skipping the already-replied c_old_1
            self.assertIsNotNone(d)
            self.assertEqual(d, "Fresh instruction")
            self.assertEqual(d.raw_comment_id, "c_new_2")


if __name__ == "__main__":
    unittest.main()
