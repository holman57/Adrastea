import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from adrastea.alpha.engine import AlphaEngine
from adrastea.alpha.scheduler import ScheduledTask
from adrastea.beta.engine import BetaEngine
from adrastea.ipc.channel import IPCClient, IPCServer
from adrastea.ipc.protocol import Message, SignalType
from adrastea.keepalive import KeepAliveProcess


class TestKeepAlive(unittest.IsolatedAsyncioTestCase):
    async def test_alpha_sleep_and_wake_lifecycle(self):
        alpha = AlphaEngine()
        alpha.ipc.port = 9101
        alpha.spawner.port = 9101
        await alpha.ipc.start()

        self.assertFalse(alpha._sleeping)
        self.assertFalse(alpha.get_status()["sleeping"])

        # Enter sleep mode
        await alpha.sleep(duration=120.0)
        self.assertTrue(alpha._sleeping)
        self.assertEqual(alpha.sleep_interval, 120.0)
        self.assertTrue(alpha.get_status()["sleeping"])

        # Wake up
        alpha.wake()
        self.assertFalse(alpha._sleeping)
        self.assertFalse(alpha.get_status()["sleeping"])

        await alpha.ipc.stop()

    async def test_heartbeat_ping_and_pong(self):
        port = 9102
        alpha = AlphaEngine()
        alpha.ipc.port = port
        alpha.spawner.port = port
        await alpha.ipc.start()

        # Ping active Alpha
        res = await KeepAliveProcess.ping(port=port, timeout=3.0)
        self.assertIsNotNone(res)
        self.assertEqual(res.get("status"), "alive")
        self.assertFalse(res.get("sleeping"))
        self.assertIn("roundtrip_ms", res)

        # Put Alpha to sleep and ping again
        await alpha.sleep(duration=300.0)
        res_sleeping = await KeepAliveProcess.ping(port=port, timeout=3.0)
        self.assertIsNotNone(res_sleeping)
        self.assertTrue(res_sleeping.get("sleeping"))
        self.assertEqual(res_sleeping.get("sleep_interval"), 300.0)

        await alpha.ipc.stop()

    async def test_remote_sleep_and_wake_signals(self):
        port = 9103
        alpha = AlphaEngine()
        alpha.ipc.port = port
        alpha.spawner.port = port
        await alpha.ipc.start()

        # Send remote sleep command
        sleep_res = await KeepAliveProcess.remote_sleep(duration=250.0, port=port, timeout=3.0)
        self.assertIsNotNone(sleep_res)
        self.assertTrue(alpha._sleeping)
        self.assertEqual(alpha.sleep_interval, 250.0)

        # Send remote wake command
        wake_res = await KeepAliveProcess.remote_wake(port=port, timeout=3.0)
        self.assertIsNotNone(wake_res)
        self.assertFalse(alpha._sleeping)

        await alpha.ipc.stop()

    async def test_sleep_interrupted_by_dispatched_task(self):
        port = 9104
        alpha = AlphaEngine()
        alpha.goal_manager.goals.clear()
        alpha.ipc.port = port
        alpha.spawner.port = port
        await alpha.ipc.start()
        alpha._running = True
        loop_task = asyncio.create_task(alpha._execution_loop())

        # Put Alpha into long keep-alive sleep (1000s)
        await alpha.sleep(duration=1000.0)
        self.assertTrue(alpha._sleeping)

        # Dispatch task via IPC while Alpha is sleeping
        client = IPCClient(port=port)
        connected = await client.connect(retries=3, delay=0.1)
        self.assertTrue(connected)

        dispatch_msg = Message(
            signal=SignalType.SIG_DISPATCH,
            sender="TestRunner",
            payload={
                "task_id": "wake_and_run_task",
                "command": "python -c \"print('Executed while waking')\"",
                "priority": 50
            }
        )
        resp = await client.query(dispatch_msg, timeout=3.0)
        self.assertIsNotNone(resp)
        self.assertEqual(resp.payload.get("action"), "dispatched")

        # Give the event loop a brief moment to wake Alpha and execute the task
        for _ in range(25):
            if not alpha._sleeping and alpha.planner.get_or_create_metrics("wake_and_run_task").execution_count >= 1:
                break
            await asyncio.sleep(0.1)

        # Alpha should now be awake and the task recorded by the RL planner
        self.assertFalse(alpha._sleeping)
        metrics = alpha.planner.get_or_create_metrics("wake_and_run_task")
        self.assertGreaterEqual(metrics.execution_count, 1)

        await client.disconnect()
        await alpha.stop()

    async def test_beta_engine_sleep_and_wake(self):
        port = 9105
        server = IPCServer(port=port)
        await server.start()

        beta = BetaEngine(ipc_port=port)
        await beta.ipc.connect(retries=3, delay=0.1)

        self.assertFalse(beta._sleeping)

        # Send SIG_SLEEP to Beta
        await beta._on_sleep(Message(signal=SignalType.SIG_SLEEP, sender="Alpha", payload={"duration": 180.0}))
        self.assertTrue(beta._sleeping)
        self.assertEqual(beta.sleep_interval, 180.0)

        # Heartbeat check while sleeping
        hb_resp = await beta._on_heartbeat(Message(signal=SignalType.SIG_HEARTBEAT, sender="Alpha"))
        self.assertEqual(hb_resp.signal, SignalType.SIG_HEARTBEAT)
        self.assertTrue(hb_resp.payload.get("sleeping"))

        # Send SIG_WAKE to Beta
        await beta._on_wake(Message(signal=SignalType.SIG_WAKE, sender="Alpha"))
        self.assertFalse(beta._sleeping)

        await beta.ipc.disconnect()
        await server.stop()

    async def test_keepalive_directive_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dir_file = Path(tmpdir) / "DIRECTIVES.txt"
            port = 9106

            supervisor = KeepAliveProcess(port=port, sleep_interval=600.0)
            supervisor.watcher.directives_file = dir_file
            supervisor.watcher._ensure_directives_file()

            # Mock alpha instance
            alpha = AlphaEngine()
            alpha.ipc.port = port
            alpha.spawner.port = port
            supervisor.alpha = alpha

            # Initially asleep
            await alpha.sleep(duration=600.0)
            self.assertTrue(alpha._sleeping)

            # Write directive to file
            with open(dir_file, "a", encoding="utf-8") as f:
                f.write("\nRun memory benchmark\n")

            # Check directive in supervisor loop step
            directive = supervisor.watcher.check_file_directive()
            self.assertEqual(directive, "Run memory benchmark")

            if directive:
                alpha.wake()
                alpha.scheduler.dispatch(
                    task_id="directive_task_1",
                    command=f'python -c "print(\'{directive}\')"',
                    priority=100
                )

            # Alpha should now be awake and task queued in scheduler
            self.assertFalse(alpha._sleeping)
            due_tasks = alpha.scheduler.get_due_tasks()
            task_ids = [t.task_id for t in due_tasks]
            self.assertIn("directive_task_1", task_ids)


if __name__ == "__main__":
    unittest.main()
