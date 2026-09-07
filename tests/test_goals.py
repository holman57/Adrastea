import time
import unittest

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
        self.assertEqual(len(manager.goals), 4)
        self.assertIn("adrastea_self_evolution", manager.goals)
        self.assertIn("user_coordination", manager.goals)
        self.assertIn("ecosystem_repos", manager.goals)
        self.assertIn("knowledge_graph_memory", manager.goals)

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

        # 2. Test stability compute allocation
        signals_stable = tuner.evaluate_goals(
            telemetry={"total_executions": 15, "total_failures": 0},
            goals_data=status,
            recent_directive=None
        )
        goal_ids = [s.payload.get("goal_id") for s in signals_stable]
        self.assertIn("ecosystem_repos", goal_ids)
        self.assertIn("adrastea_self_evolution", goal_ids)


if __name__ == "__main__":
    unittest.main()
