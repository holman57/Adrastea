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


if __name__ == "__main__":
    unittest.main()
