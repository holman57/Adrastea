import asyncio
import unittest
from adrastea.alpha.engine import AlphaEngine
from adrastea.alpha.scheduler import ScheduledTask
from adrastea.ipc.protocol import SignalType, Message


class TestSystemIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_alpha_lifecycle_and_shutdown(self):
        # Create an AlphaEngine with test port
        alpha = AlphaEngine()
        alpha.ipc.port = 8995
        alpha.spawner.port = 8995

        # Register a fast local task
        task = ScheduledTask(
            task_id="integration_task_1",
            command="python -c \"print('Integration test running')\"",
            interval_seconds=1.0,
            priority=10
        )
        alpha.scheduler.register(task)

        # Start Alpha without spawning full long-running Beta subprocess in this short test
        await alpha.ipc.start()
        alpha._running = True
        loop_task = asyncio.create_task(alpha._execution_loop())

        # Allow execution loop to run at least one tick
        await asyncio.sleep(1.5)

        # Verify task was executed and RL planner recorded outcome
        metrics = alpha.planner.get_or_create_metrics("integration_task_1")
        self.assertGreaterEqual(metrics.execution_count, 1)
        self.assertEqual(metrics.success_count, metrics.execution_count)

        # Verify status endpoint
        status = alpha.get_status()
        self.assertTrue(status["running"])
        self.assertIn("integration_task_1", status["telemetry"]["task_scores"])

        # Clean shutdown
        alpha._running = False
        loop_task.cancel()
        await alpha.ipc.stop()
        self.assertFalse(alpha._running)


if __name__ == "__main__":
    unittest.main()
