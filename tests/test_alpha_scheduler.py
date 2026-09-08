import time
import unittest
from adrastea.alpha.planner import RLPlanner
from adrastea.alpha.scheduler import ScheduledTask, TaskScheduler


class TestTaskScheduler(unittest.TestCase):
    def setUp(self):
        self.planner = RLPlanner()
        self.scheduler = TaskScheduler(planner=self.planner)

    def test_schedule_and_due_tasks(self):
        # Task 1 is due now
        t1 = ScheduledTask(task_id="t1", command="echo 1", next_run_time=time.time() - 10)
        # Task 2 is due in the future
        t2 = ScheduledTask(task_id="t2", command="echo 2", next_run_time=time.time() + 100)

        self.scheduler.register(t1)
        self.scheduler.register(t2)

        due = self.scheduler.get_due_tasks()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].task_id, "t1")

    def test_dispatch_and_mutate(self):
        self.scheduler.dispatch(task_id="urgent_task", command="python -c 'print(1)'", priority=50)
        due = self.scheduler.get_due_tasks()
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].task_id, "urgent_task")

        # Mutate
        success = self.scheduler.mutate("urgent_task", {"priority": 99})
        self.assertTrue(success)
        self.assertEqual(self.scheduler.tasks["urgent_task"].priority, 99)

    def test_default_scheduled_tasks(self):
        from adrastea.tasks.builtins import get_default_scheduled_tasks
        tasks = get_default_scheduled_tasks()
        task_ids = [t.task_id for t in tasks]
        self.assertIn("system_health_check", task_ids)
        self.assertIn("ollama_health_check", task_ids)
        self.assertIn("user_notification_dispatch", task_ids)
        self.assertIn("market_research_daily_zeitgeist", task_ids)

        zg_task = next(t for t in tasks if t.task_id == "market_research_daily_zeitgeist")
        self.assertEqual(zg_task.interval_seconds, 86400.0)
        self.assertIn("market_research.inquiry.zeitgeist_radar", zg_task.command)


if __name__ == "__main__":
    unittest.main()
