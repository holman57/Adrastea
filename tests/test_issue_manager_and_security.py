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

    @patch("subprocess.run")
    def test_new_issue_created_by_holman57_ingested_as_directive(self, mock_subproc):
        # Issue created by Luke (@holman57) with zero comments
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "number": 10,
                "title": "Update model weights to 2.5",
                "body": "Please recalibrate RL reward weight",
                "author": {"login": "holman57"},
                "state": "OPEN",
                "createdAt": "2026-09-09T20:00:00Z",
                "updatedAt": "2026-09-09T20:00:00Z",
                "comments": []
            })
        )
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[10]):
            directive = self.watcher.check_github_issue_directive()
            self.assertIsNotNone(directive)
            self.assertIn("Update model weights to 2.5", directive.text)
            self.assertIn("Please recalibrate RL reward weight", directive.text)
            self.assertEqual(directive.author, "holman57")
            self.assertEqual(directive.issue_number, 10)
            self.assertEqual(directive.raw_comment_id, "issue_body_10")

            # Second check: must be deduplicated
            directive_2 = self.watcher.check_github_issue_directive()
            self.assertIsNone(directive_2)

    @patch("subprocess.run")
    def test_deleted_issue_skipped_gracefully(self, mock_subproc):
        # Mock gh CLI returning error for deleted/inaccessible issue
        mock_subproc.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="GraphQL: Could not resolve to an issue (repository.issue)"
        )
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[999]):
            directive = self.watcher.check_github_issue_directive()
            self.assertIsNone(directive)

    def test_escalating_backoff_for_waiting_issues(self):
        # Initial wait duration is 2 days (172,800 seconds)
        duration_0 = self.topic_mgr.get_issue_wait_duration(5)
        self.assertEqual(duration_0, 2.0 * 86400.0)

        # After Adrastea asks once, wait escalates to 4 days (345,600 seconds)
        self.topic_mgr.record_adrastea_inquiry(5)
        duration_1 = self.topic_mgr.get_issue_wait_duration(5)
        self.assertEqual(duration_1, 4.0 * 86400.0)

        # After Adrastea asks twice, wait escalates to 8 days (691,200 seconds)
        self.topic_mgr.record_adrastea_inquiry(5)
        duration_2 = self.topic_mgr.get_issue_wait_duration(5)
        self.assertEqual(duration_2, 8.0 * 86400.0)

        # When operator replies, wait state resets back to count 0 (2 days)
        self.topic_mgr.reset_issue_wait(5)
        duration_reset = self.topic_mgr.get_issue_wait_duration(5)
        self.assertEqual(duration_reset, 2.0 * 86400.0)
        self.assertEqual(self.topic_mgr.get_wait_count(5), 0)

    @patch("subprocess.run")
    def test_external_contributor_receives_pleasantry_no_action(self, mock_subproc):
        # External contributor comments on an existing autonomous goal issue
        mock_subproc.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({
                "number": 4,
                "title": "[Goal] Companion Repos",
                "body": "### [Goal] Companion Repositories",
                "author": {"login": "holman57"},
                "state": "OPEN",
                "comments": [
                    {"id": "ext_comment_1", "author": {"login": "random_contributor"}, "body": "Can you support C++?"}
                ]
            })
        )
        with patch.object(self.watcher, "_get_monitored_issue_numbers", return_value=[4]):
            with patch.object(self.topic_mgr, "post_contributor_pleasantry") as mock_pleasantry:
                directive = self.watcher.check_github_issue_directive()

                # NO system action directive generated for external user
                self.assertIsNone(directive)
                # Pleasantry was dispatched to external user
                mock_pleasantry.assert_called_once_with(4, "random_contributor")

    def test_load_adaptive_cadence(self):
        # Normal load
        with patch("psutil.cpu_percent", return_value=15.0), patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value = MagicMock(percent=35.0)
            self.assertEqual(self.watcher.get_adaptive_interval(), 900.0)

        # Moderate load (30 mins)
        with patch("psutil.cpu_percent", return_value=55.0), patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value = MagicMock(percent=50.0)
            self.assertEqual(self.watcher.get_adaptive_interval(), 1800.0)

        # Heavy load (60 mins)
        with patch("psutil.cpu_percent", return_value=85.0), patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value = MagicMock(percent=90.0)
            self.assertEqual(self.watcher.get_adaptive_interval(), 3600.0)

    def test_multi_repo_directive_detection_and_queueing(self):
        # Configure watcher for multiple repositories
        multi_watcher = DirectiveWatcher(
            directives_file=self.directives_file,
            seen_comments_file=self.seen_comments_file,
            target_repos=["holman57/Adrastea", "holman57/hardcode"],
        )

        mock_mgr_adrastea = MagicMock()
        mock_mgr_adrastea.repo = "holman57/Adrastea"
        mock_mgr_adrastea.list_open_issues.return_value = [{"number": 9}]
        mock_mgr_adrastea.get_issue_data.return_value = {
            "number": 9,
            "title": "Adrastea Core Task",
            "body": "Optimize cognitive loop",
            "author": {"login": "holman57"},
            "comments": [],
        }
        mock_mgr_adrastea.is_adrastea_content.return_value = False
        mock_mgr_adrastea.is_waiting_for_user_response.return_value = (False, "")

        mock_mgr_hardcode = MagicMock()
        mock_mgr_hardcode.repo = "holman57/hardcode"
        mock_mgr_hardcode.list_open_issues.return_value = [{"number": 4}]
        mock_mgr_hardcode.get_issue_data.return_value = {
            "number": 4,
            "title": "Roadmap RFC",
            "body": "RFC Body",
            "author": {"login": "holman57"},
            "comments": [
                {"id": "hc_c1", "author": {"login": "holman57"}, "body": "Add SM-2 algorithm"}
            ],
        }
        mock_mgr_hardcode.is_adrastea_content.return_value = False
        mock_mgr_hardcode.is_waiting_for_user_response.return_value = (False, "")

        def fake_get_mgr(repo):
            if repo == "holman57/hardcode":
                return mock_mgr_hardcode
            return mock_mgr_adrastea

        with patch.object(multi_watcher, "get_correspondence_manager", side_effect=fake_get_mgr):
            # First tick: should return directive 1 from holman57/Adrastea
            d1 = multi_watcher.check_directives(force=True)
            self.assertIsNotNone(d1)
            self.assertEqual(d1.repo, "holman57/Adrastea")
            self.assertEqual(d1.issue_number, 9)

            # Second tick: should drain directive 2 (issue body) from holman57/hardcode
            d2 = multi_watcher.check_directives(force=False)
            self.assertIsNotNone(d2)
            self.assertEqual(d2.repo, "holman57/hardcode")
            self.assertEqual(d2.issue_number, 4)
            self.assertEqual(d2.goal_id, "companion_feature_builder")
            self.assertIn("Roadmap RFC", d2.text)

            # Third tick: should drain directive 3 (comment) from holman57/hardcode
            d3 = multi_watcher.check_directives(force=False)
            self.assertIsNotNone(d3)
            self.assertEqual(d3.repo, "holman57/hardcode")
            self.assertEqual(d3.issue_number, 4)
            self.assertEqual(d3.goal_id, "companion_feature_builder")
            self.assertIn("Add SM-2 algorithm", d3.text)

            # Fourth tick: queue is empty, no directives pending
            d4 = multi_watcher.check_directives(force=False)
            self.assertIsNone(d4)

    @patch("subprocess.run")
    def test_scan_and_converse_in_issues_actively_replies(self, mock_subproc):
        from adrastea.alpha.goals.companion_feature_builder import scan_and_converse_in_issues

        # Mock gh issue list returning an issue with a comment from Luke
        mock_subproc.side_effect = [
            # 1. gh issue list
            MagicMock(
                returncode=0,
                stdout=json.dumps([
                    {
                        "number": 2,
                        "title": "Expand topics and definitions",
                        "body": "Issue body",
                        "author": {"login": "holman57"},
                        "comments": [
                            {"id": "c1", "author": {"login": "holman57"}, "body": "Add new question types"}
                        ],
                    }
                ]),
            ),
            # 2. gh issue comment (response)
            MagicMock(returncode=0, stdout="https://github.com/holman57/hardcode/issues/2#issuecomment-999"),
        ]

        res = scan_and_converse_in_issues("hardcode", auto_ask=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["repo"], "holman57/hardcode")
        self.assertEqual(len(res["operator_guidance"]), 1)
        self.assertIn("replied_to_guidance_#2", res["actions_taken"])


if __name__ == "__main__":
    unittest.main()

