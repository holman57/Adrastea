import unittest
from adrastea.alpha.planner import RLPlanner, RLWeights
from adrastea.alpha.runner import TaskExecutionResult


class TestRLPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = RLPlanner()

    def test_positive_reward_on_success(self):
        result = TaskExecutionResult(
            task_id="task_good",
            command="echo good",
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_seconds=1.0
        )
        reward = self.planner.compute_reward(result)
        self.assertGreater(reward, 0.0)

        # Record outcome
        self.planner.record_outcome(result)
        metrics = self.planner.get_or_create_metrics("task_good")
        self.assertEqual(metrics.success_count, 1)
        self.assertEqual(metrics.failure_count, 0)
        self.assertEqual(metrics.consecutive_failures, 0)

    def test_negative_reward_and_stuck_detection(self):
        for i in range(3):
            fail_result = TaskExecutionResult(
                task_id="task_bad",
                command="exit 1",
                exit_code=1,
                stdout="",
                stderr="error",
                duration_seconds=0.5
            )
            reward = self.planner.compute_reward(fail_result)
            self.assertLess(reward, 0.0)
            self.planner.record_outcome(fail_result)

        # Should be detected as stuck
        self.assertTrue(self.planner.is_stuck("task_bad", threshold_consecutive_fails=3))

    def test_beta_weight_tuning(self):
        initial_penalty = self.planner.weights.w_error_penalty
        self.planner.tune_weights({"w_error_penalty": 28.5, "exploration_rate": 0.4})

        self.assertEqual(self.planner.weights.w_error_penalty, 28.5)
        self.assertEqual(self.planner.weights.exploration_rate, 0.4)


if __name__ == "__main__":
    unittest.main()
