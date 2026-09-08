import json
import time
import unittest
from unittest.mock import MagicMock, patch

from adrastea.alpha.goals.companion_feature_builder import (
    CompanionFeatureBuilderGoal,
    analyze_companion_repo,
    create_feature_branch_and_pr,
    scan_and_converse_in_issues,
)
from adrastea.alpha.goals.daily_github_commit import (
    DailyGitHubCommitGoal,
    get_last_commit_info,
    is_commit_due,
    run_daily_commit,
)
from adrastea.alpha.goals.ecosystem_repos import EcosystemReposGoal
from adrastea.alpha.goals.knowledge_graph import KnowledgeGraphMemoryGoal
from adrastea.alpha.goals.manager import GoalManager
from adrastea.alpha.goals.self_evolution import AdrasteaSelfEvolutionGoal
from adrastea.alpha.goals.user_coordination import UserCoordinationGoal
from adrastea.beta.tuner import HeuristicTuner
from adrastea.ipc.protocol import SignalType


class TestAlphaGoals(unittest.TestCase):

    def test_default_goals_registration(self):
        manager = GoalManager()
        self.assertEqual(len(manager.goals), 7)
        self.assertIn("adrastea_self_evolution", manager.goals)
        self.assertIn("user_coordination", manager.goals)
        self.assertIn("ecosystem_repos", manager.goals)
        self.assertIn("knowledge_graph_memory", manager.goals)
        self.assertIn("daily_github_commit", manager.goals)
        self.assertIn("companion_feature_builder", manager.goals)
        self.assertIn("github_profile_promoter", manager.goals)

    def test_self_evolution_goal_tasks(self):
        goal = AdrasteaSelfEvolutionGoal()
        tasks = goal.generate_tasks()
        self.assertGreaterEqual(len(tasks), 2)
        task_ids = [t.task_id for t in tasks]
        self.assertTrue(any("self_repo_audit" in tid for tid in task_ids))
        self.assertTrue(any("self_regression_test" in tid for tid in task_ids))

    def test_user_coordination_goal_tasks(self):
        goal = UserCoordinationGoal()
        # Default: anti-spam mode (directives polling only)
        tasks_default = goal.generate_tasks()
        self.assertEqual(len(tasks_default), 1)
        self.assertTrue("coord_directives_poll" in tasks_default[0].task_id)

        # When explicitly configured to dispatch outreach
        goal.tune({"parameters": {"enable_periodic_outreach": True}})
        tasks_outreach = goal.generate_tasks()
        self.assertEqual(len(tasks_outreach), 2)
        task_ids = [t.task_id for t in tasks_outreach]
        self.assertTrue(any("coord_outreach_dispatch" in tid for tid in task_ids))

    def test_ecosystem_repos_goal_round_robin_and_focus(self):
        goal = EcosystemReposGoal()
        # Test focus repo
        goal.tune({"parameters": {"focus_repo": "distributed-content-management"}})
        tasks = goal.generate_tasks()
        self.assertGreaterEqual(len(tasks), 2)
        self.assertEqual(tasks[0].metadata["repo"], "distributed-content-management")

        # Clear focus and test round-robin
        goal.tune({"parameters": {"focus_repo": None}})
        repo_1 = goal.generate_tasks()[0].metadata["repo"]
        repo_2 = goal.generate_tasks()[0].metadata["repo"]
        self.assertNotEqual(repo_1, repo_2)

    def test_knowledge_graph_memory_goal(self):
        goal = KnowledgeGraphMemoryGoal()
        tasks = goal.generate_tasks()
        self.assertGreaterEqual(len(tasks), 2)
        task_ids = [t.task_id for t in tasks]
        self.assertTrue(any("kg_consolidate" in tid for tid in task_ids))
        self.assertTrue(any("kg_health_check" in tid for tid in task_ids))

    def test_goal_manager_task_generation_and_weight_priority(self):
        manager = GoalManager()
        # Force all goals to be due immediately
        now = time.time() + 10000.0

        # Tune user_coordination to highest weight
        manager.tune_goal("user_coordination", {"weight": 5.0})
        manager.tune_goal("adrastea_self_evolution", {"weight": 0.5})

        tasks = manager.generate_due_tasks(now=now)
        self.assertGreater(len(tasks), 4)

        # The first generated tasks should originate from the highest weight goal
        first_goal_id = tasks[0].metadata.get("goal_id")
        self.assertEqual(first_goal_id, "user_coordination")

    def test_heuristic_tuner_goal_steering(self):
        tuner = HeuristicTuner()
        manager = GoalManager()
        status = manager.get_goals_status()

        # 1. Test directive steering for companion repo
        signals = tuner.evaluate_goals(
            telemetry={"total_executions": 5, "total_failures": 0},
            goals_data=status,
            recent_directive="Focus your development on speech-flow"
        )
        self.assertGreater(len(signals), 0)
        found_focus = False
        for s in signals:
            self.assertEqual(s.signal, SignalType.SIG_TUNE_GOALS)
            if s.payload.get("goal_id") == "ecosystem_repos":
                self.assertEqual(s.payload.get("parameters", {}).get("focus_repo"), "speech-flow")
                found_focus = True
        self.assertTrue(found_focus)

        # 2. Test directive steering for daily commits
        signals_commit = tuner.evaluate_goals(
            telemetry={"total_executions": 5, "total_failures": 0},
            goals_data=status,
            recent_directive="Adrastea should commit everyday to keep GitHub active"
        )
        found_commit = any(
            s.payload.get("goal_id") == "daily_github_commit" and s.payload.get("parameters", {}).get("force_commit")
            for s in signals_commit
        )
        self.assertTrue(found_commit)

        # 3. Test stability compute allocation
        signals_stable = tuner.evaluate_goals(
            telemetry={"total_executions": 15, "total_failures": 0},
            goals_data=status,
            recent_directive=None
        )
        goal_ids = [s.payload.get("goal_id") for s in signals_stable]
        self.assertIn("ecosystem_repos", goal_ids)
        self.assertIn("adrastea_self_evolution", goal_ids)

    def test_daily_github_commit_goal_cadence(self):
        goal = DailyGitHubCommitGoal()
        # Case 1: When last commit is fresh (e.g. 1 hour ago) and not forced
        fake_now = 1788800000.0
        # Mock get_last_commit_info to return commit timestamp 1 hour ago
        from unittest.mock import MagicMock, patch
        with patch("adrastea.alpha.goals.daily_github_commit.get_last_commit_info") as mock_info:
            mock_info.return_value = {"timestamp": fake_now - 3600.0}
            tasks = goal.generate_tasks(context={"now": fake_now})
            self.assertEqual(len(tasks), 0)

            # Case 2: When last commit is 25 hours ago (overdue)
            mock_info.return_value = {"timestamp": fake_now - 90000.0}
            tasks_overdue = goal.generate_tasks(context={"now": fake_now})
            self.assertEqual(len(tasks_overdue), 1)
            self.assertIn("daily_github_commit", tasks_overdue[0].task_id)
            self.assertEqual(tasks_overdue[0].metadata["goal_id"], "daily_github_commit")

            # Case 3: When force_commit parameter is enabled
            mock_info.return_value = {"timestamp": fake_now - 3600.0}
            goal.tune({"parameters": {"force_commit": True}})
            tasks_forced = goal.generate_tasks(context={"now": fake_now})
            self.assertEqual(len(tasks_forced), 1)
            self.assertFalse(goal.parameters["force_commit"])  # should be reset

    @patch("subprocess.run")
    def test_run_daily_commit_mocked(self, mock_subproc):
        # Mock git status (has changes in ACTIVITY_LOG.md)
        def side_effect(cmd, *args, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "status" in cmd:
                m.stdout = " M ACTIVITY_LOG.md\n"
            elif "rev-parse" in cmd:
                m.stdout = "a1b2c3d4e5f6\n"
            else:
                m.stdout = ""
            m.stderr = ""
            return m

        mock_subproc.side_effect = side_effect

        res = run_daily_commit(auto_push=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["committed"])
        self.assertTrue(res["pushed"])
        self.assertEqual(res["commit_hash"], "a1b2c3d4e5f6")

    def test_companion_feature_builder_goal_tasks(self):
        goal = CompanionFeatureBuilderGoal()
        # 1. Test task generation with all 5 companion repos
        self.assertEqual(len(goal.parameters["target_repos"]), 5)
        self.assertIn("hardcode", goal.parameters["target_repos"])
        self.assertIn("market-research", goal.parameters["target_repos"])

        # 2. Test round-robin task generation
        tasks_1 = goal.generate_tasks()
        self.assertGreaterEqual(len(tasks_1), 2)
        repo_1 = tasks_1[0].metadata["repo"]

        tasks_2 = goal.generate_tasks()
        self.assertGreaterEqual(len(tasks_2), 2)
        repo_2 = tasks_2[0].metadata["repo"]
        self.assertNotEqual(repo_1, repo_2)

        # 3. Test focus_repo override
        goal.tune({"parameters": {"focus_repo": "hardcode"}})
        tasks_focus = goal.generate_tasks()
        self.assertEqual(tasks_focus[0].metadata["repo"], "hardcode")

    @patch("subprocess.run")
    def test_companion_feature_builder_scan_and_converse_mocked(self, mock_subproc):
        # Mock gh issue list returning an issue where Luke commented
        def side_effect(cmd, *args, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "list" in cmd:
                m.stdout = json.dumps([
                    {
                        "number": 10,
                        "title": "[Adrastea RFC] Autonomous Feature Roadmap for speech-flow",
                        "comments": [
                            {"author": {"login": "holman57"}, "body": "Prioritize push-to-talk hotkey"}
                        ]
                    }
                ])
            elif "create" in cmd:
                m.stdout = "https://github.com/holman57/speech-flow/issues/11\n"
            else:
                m.stdout = ""
            m.stderr = ""
            return m

        mock_subproc.side_effect = side_effect

        res = scan_and_converse_in_issues("speech-flow", operator="holman57", auto_ask=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["open_issues_count"], 1)
        self.assertEqual(len(res["operator_guidance"]), 1)
        self.assertEqual(res["operator_guidance"][0]["directive"], "Prioritize push-to-talk hotkey")

    @patch("subprocess.run")
    def test_create_feature_branch_and_pr_mocked(self, mock_subproc):
        def side_effect(cmd, *args, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "pr" in cmd and "create" in cmd:
                m.stdout = "https://github.com/holman57/speech-flow/pull/15\n"
            elif "rev-parse" in cmd:
                m.stdout = "feat/push-to-talk\n"
            else:
                m.stdout = ""
            m.stderr = ""
            return m

        mock_subproc.side_effect = side_effect

        # Mock repo directory existence
        with patch("adrastea.alpha.goals.companion_feature_builder.get_repo_path") as mock_path:
            mock_dir = MagicMock()
            mock_dir.is_dir.return_value = True
            mock_path.return_value = mock_dir

            pr_res = create_feature_branch_and_pr(
                repo_name="speech-flow",
                branch_name="feat/push-to-talk",
                commit_message="feat(audio): add push-to-talk hotkey",
                pr_title="feat(audio): Push-to-Talk Hotkey Integration",
                pr_body="Adds global keyboard hook for push-to-talk audio streaming.",
                modified_files=["speech_flow/audio.py"],
                assignee="holman57",
            )
            self.assertTrue(pr_res["success"])
            self.assertEqual(pr_res["pr_url"], "https://github.com/holman57/speech-flow/pull/15")
            self.assertEqual(pr_res["assignee"], "holman57")


if __name__ == "__main__":
    unittest.main()
