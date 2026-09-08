"""
Unit tests for GitHubProfilePromoterGoal and engagement/star acceleration utilities.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from adrastea.alpha.goals.github_profile_promoter import (
    GitHubProfilePromoterGoal,
    audit_github_profile_and_repos,
    generate_growth_dispatch_markdown,
    post_or_update_growth_issue,
    REPO_PROMOTION_PLAYBOOKS,
    TARGET_USER,
)
from adrastea.alpha.goals.manager import GoalManager


class TestGitHubProfilePromoterGoal(unittest.TestCase):

    def setUp(self):
        self.goal = GitHubProfilePromoterGoal()

    def test_goal_initialization(self):
        self.assertEqual(self.goal.goal_id, "github_profile_promoter")
        self.assertTrue(self.goal.enabled)
        self.assertEqual(self.goal.weight, 1.3)
        self.assertEqual(self.goal.interval_seconds, 1800.0)
        self.assertIn("Adrastea", self.goal.parameters.get("target_repos", []))
        self.assertIn("market-research", self.goal.parameters.get("target_repos", []))

    def test_goal_registered_in_manager(self):
        manager = GoalManager()
        self.assertIn("github_profile_promoter", manager.goals)
        registered_goal = manager.get_goal("github_profile_promoter")
        self.assertIsNotNone(registered_goal)
        self.assertEqual(registered_goal.goal_id, "github_profile_promoter")

    def test_generate_tasks(self):
        tasks = self.goal.generate_tasks()
        self.assertTrue(len(tasks) >= 2)
        task_ids = [t.task_id for t in tasks]
        self.assertTrue(any("gh_growth_audit" in tid for tid in task_ids))
        self.assertTrue(any("gh_growth_dispatch" in tid for tid in task_ids))

        for t in tasks:
            self.assertIn(TARGET_USER, t.command)
            self.assertGreater(t.priority, 0)

    def test_playbook_coverage(self):
        # Verify playbooks exist for all core companion repositories
        required_repos = [
            "Adrastea",
            "market-research",
            "distributed-content-management",
            "speech-flow",
            "interpretive-interface",
            "hardcode",
        ]
        for repo in required_repos:
            self.assertIn(repo, REPO_PROMOTION_PLAYBOOKS)
            playbook = REPO_PROMOTION_PLAYBOOKS[repo]
            self.assertTrue(bool(playbook.get("title")))
            self.assertTrue(bool(playbook.get("value_prop")))
            self.assertTrue(len(playbook.get("recommended_topics", [])) > 0)
            self.assertTrue(bool(playbook.get("show_hn", {}).get("title")))
            self.assertTrue(bool(playbook.get("show_hn", {}).get("post_body")))
            self.assertTrue(len(playbook.get("reddit_targets", [])) > 0)
            self.assertTrue(len(playbook.get("awesome_lists", [])) > 0)

    def test_generate_growth_dispatch_markdown(self):
        audit_data = {
            "user": "holman57",
            "timestamp": "2026-09-08 12:00:00 UTC",
            "profile": {"followers": 77},
            "total_stars": 3,
        }
        md = generate_growth_dispatch_markdown("Adrastea", audit_data)
        self.assertIn("# 🚀 Growth & Star Acceleration Blueprint: `Adrastea`", md)
        self.assertIn("holman57", md)
        self.assertIn("Show HN: Adrastea", md)
        self.assertIn("r/LocalLLaMA", md)
        self.assertIn("shields.io", md)
        self.assertIn("awesome-ai-agents", md)

    @patch("subprocess.run")
    def test_post_or_update_growth_issue_create(self, mock_run):
        # Case 1: Issue doesn't exist yet -> creates new issue
        mock_list = MagicMock()
        mock_list.stdout = "[]"
        mock_list.returncode = 0

        mock_create = MagicMock()
        mock_create.stdout = "https://github.com/holman57/Adrastea/issues/99\n"
        mock_create.returncode = 0

        mock_user = MagicMock()
        mock_user.stdout = '{"login": "holman57", "followers": 77}'
        mock_user.returncode = 0

        mock_repos = MagicMock()
        mock_repos.stdout = "[]"
        mock_repos.returncode = 0

        mock_run.side_effect = [mock_user, mock_repos, mock_list, mock_create]

        res = post_or_update_growth_issue("Adrastea", "holman57")
        self.assertEqual(res["action"], "created")
        self.assertEqual(res["issue_number"], 99)


if __name__ == "__main__":
    unittest.main()
