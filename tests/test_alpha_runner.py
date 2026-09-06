import asyncio
import sys
import unittest
from adrastea.alpha.runner import LocalProgramRunner


class TestLocalProgramRunner(unittest.IsolatedAsyncioTestCase):
    async def test_successful_execution(self):
        runner = LocalProgramRunner()
        cmd = f'"{sys.executable}" -c "print(\'Hello Adrastea\')"'
        result = await runner.execute("task_test_1", cmd, timeout=5.0)

        self.assertTrue(result.is_success)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Hello Adrastea", result.stdout)
        self.assertFalse(result.interrupted)
        self.assertGreater(result.duration_seconds, 0)

    async def test_failing_execution(self):
        runner = LocalProgramRunner()
        cmd = f'"{sys.executable}" -c "import sys; sys.stderr.write(\'Fatal Error\'); sys.exit(2)"'
        result = await runner.execute("task_test_2", cmd, timeout=5.0)

        self.assertFalse(result.is_success)
        self.assertEqual(result.exit_code, 2)
        self.assertIn("Fatal Error", result.stderr)

    async def test_task_timeout(self):
        runner = LocalProgramRunner()
        # Sleep for 10 seconds with 1 second timeout
        cmd = f'"{sys.executable}" -c "import time; time.sleep(10)"'
        result = await runner.execute("task_test_3", cmd, timeout=1.0)

        self.assertFalse(result.is_success)
        self.assertEqual(result.exit_code, -99)
        self.assertIn("timed out", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
