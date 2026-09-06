import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ..config import config
from ..ipc.channel import IPCServer
from ..ipc.protocol import Message, SignalType
from .local_llm import LocalLLMClient
from .planner import RLPlanner
from .runner import LocalProgramRunner, TaskExecutionResult
from .scheduler import ScheduledTask, TaskScheduler
from .spawner import BetaSpawner

logger = logging.getLogger("Adrastea.Alpha")


class AlphaEngine:
    """Deterministic Execution Engine for Adrastea."""

    def __init__(self):
        self.ipc = IPCServer(host=config.ipc_host, port=config.ipc_port)
        self.planner = RLPlanner()
        self.runner = LocalProgramRunner()
        self.scheduler = TaskScheduler(planner=self.planner)
        self.spawner = BetaSpawner(host=config.ipc_host, port=config.ipc_port)
        self.local_llm = LocalLLMClient(base_url=config.ollama_base_url, model=config.ollama_model)

        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._beta_spawned = False
        self.start_time = 0.0

        # Setup IPC message handlers
        self._setup_ipc_handlers()

    def _setup_ipc_handlers(self) -> None:
        self.ipc.register_handler(SignalType.SIG_INTERRUPT, self._on_interrupt)
        self.ipc.register_handler(SignalType.SIG_DISPATCH, self._on_dispatch)
        self.ipc.register_handler(SignalType.SIG_MUTATE, self._on_mutate)
        self.ipc.register_handler(SignalType.SIG_TUNE_WEIGHTS, self._on_tune_weights)
        self.ipc.register_handler(SignalType.SIG_QUERY_STATUS, self._on_query_status)
        self.ipc.register_handler(SignalType.SIG_SHUTDOWN, self._on_shutdown_signal)

    async def _on_interrupt(self, msg: Message) -> Optional[Message]:
        task_id = msg.payload.get("task_id")
        logger.info(f"Received SIG_INTERRUPT from Beta for task [{task_id}]")
        if task_id:
            success = await self.runner.interrupt(task_id)
            return Message(
                signal=SignalType.SIG_TELEMETRY,
                sender="Alpha",
                payload={"action": "interrupted", "task_id": task_id, "success": success}
            )
        return None

    async def _on_dispatch(self, msg: Message) -> Optional[Message]:
        task_id = msg.payload.get("task_id")
        command = msg.payload.get("command")
        priority = msg.payload.get("priority", 20)
        logger.info(f"Received SIG_DISPATCH from Beta: [{task_id}] -> {command}")
        if task_id and command:
            self.scheduler.dispatch(task_id, command, priority=priority, metadata=msg.payload.get("metadata", {}))
            return Message(
                signal=SignalType.SIG_TELEMETRY,
                sender="Alpha",
                payload={"action": "dispatched", "task_id": task_id}
            )
        return None

    async def _on_mutate(self, msg: Message) -> Optional[Message]:
        task_id = msg.payload.get("task_id")
        updates = msg.payload.get("updates", {})
        logger.info(f"Received SIG_MUTATE from Beta for [{task_id}]: {updates}")
        if task_id and updates:
            success = self.scheduler.mutate(task_id, updates)
            return Message(
                signal=SignalType.SIG_TELEMETRY,
                sender="Alpha",
                payload={"action": "mutated", "task_id": task_id, "success": success}
            )
        return None

    async def _on_tune_weights(self, msg: Message) -> Optional[Message]:
        weights = msg.payload.get("weights", {})
        logger.info(f"Received SIG_TUNE_WEIGHTS from Beta: {weights}")
        if weights:
            self.planner.tune_weights(weights)
            return Message(
                signal=SignalType.SIG_TELEMETRY,
                sender="Alpha",
                payload={"action": "weights_tuned", "current_weights": self.planner.weights.__dict__}
            )
        return None

    async def _on_query_status(self, msg: Message) -> Message:
        return Message(
            signal=SignalType.SIG_TELEMETRY,
            sender="Alpha",
            payload=self.get_status()
        )

    async def _on_shutdown_signal(self, msg: Message) -> None:
        logger.info("Received SIG_SHUTDOWN from Beta.")
        await self.stop()

    def get_status(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time if self.start_time else 0
        return {
            "uptime_seconds": round(uptime, 2),
            "running": self._running,
            "beta_spawned": self._beta_spawned,
            "active_tasks": self.runner.list_active_tasks(),
            "scheduled_tasks_count": len(self.scheduler.tasks),
            "telemetry": self.planner.get_summary_telemetry(),
            "local_llm_online": self.local_llm.is_available()
        }

    async def start(self) -> None:
        """Start the deterministic execution engine."""
        self._running = True
        self.start_time = time.time()
        logger.info("Initializing System Alpha...")

        # 1. Start IPC Server
        await self.ipc.start()

        # 2. Check Local LLM Status
        llm_ok = self.local_llm.is_available()
        logger.info(f"Local LLM (Ollama @ {config.ollama_base_url}) status: {'READY' if llm_ok else 'UNAVAILABLE'}")

        # 3. Stabilization period before spawning Beta
        logger.info(f"System Alpha stabilizing ({config.alpha_stabilization_seconds}s)...")
        await asyncio.sleep(config.alpha_stabilization_seconds)
        logger.info("System Alpha stabilized.")

        # 4. Spawn Beta Process
        spawn_ok = await self.spawner.spawn()
        self._beta_spawned = spawn_ok

        # 5. Launch main deterministic execution loop
        self._loop_task = asyncio.create_task(self._execution_loop())

    async def _execution_loop(self) -> None:
        """Main deterministic loop ticking and executing due tasks."""
        logger.info("System Alpha deterministic execution loop started.")
        last_telemetry_time = time.time()

        while self._running:
            try:
                # Retrieve due tasks ordered by RL planner
                due_tasks = self.scheduler.get_due_tasks()
                for task in due_tasks[:config.alpha_max_concurrent_tasks]:
                    # Execute in background or await
                    asyncio.create_task(self._run_task(task))

                # Periodically emit telemetry to Beta every 10 seconds
                if time.time() - last_telemetry_time > 10.0:
                    await self.ipc.broadcast(
                        Message(
                            signal=SignalType.SIG_TELEMETRY,
                            sender="Alpha",
                            payload=self.get_status()
                        )
                    )
                    last_telemetry_time = time.time()

                await asyncio.sleep(config.alpha_tick_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Alpha execution loop: {e}", exc_info=True)
                await asyncio.sleep(config.alpha_tick_interval)

    async def _run_task(self, task: ScheduledTask) -> None:
        """Execute a scheduled task, evaluate RL score, and report to Beta."""
        task.mark_executed()
        result: TaskExecutionResult = await self.runner.execute(task.task_id, task.command)

        # RL Planner evaluates outcome and computes reward
        reward = self.planner.record_outcome(result)

        # Notify Beta of task outcome
        sig = SignalType.SIG_TASK_COMPLETED if result.is_success else SignalType.SIG_TASK_FAILED
        await self.ipc.broadcast(
            Message(
                signal=sig,
                sender="Alpha",
                payload={
                    "task_id": task.task_id,
                    "command": task.command,
                    "exit_code": result.exit_code,
                    "duration": result.duration_seconds,
                    "stdout_sample": result.stdout[:200],
                    "stderr_sample": result.stderr[:200],
                    "reward": reward,
                    "interrupted": result.interrupted
                }
            )
        )

        # Check for stuck condition (repeated failures)
        if self.planner.is_stuck(task.task_id, threshold_consecutive_fails=3):
            logger.warning(f"Task [{task.task_id}] appears STUCK! Emitting SIG_STUCK to Beta...")
            await self.ipc.broadcast(
                Message(
                    signal=SignalType.SIG_STUCK,
                    sender="Alpha",
                    payload={
                        "task_id": task.task_id,
                        "command": task.command,
                        "consecutive_failures": self.planner.get_or_create_metrics(task.task_id).consecutive_failures,
                        "last_error": result.stderr[:400]
                    }
                )
            )

    async def stop(self) -> None:
        """Gracefully stop Alpha and Beta."""
        logger.info("Stopping System Alpha...")
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        # Shutdown Beta
        await self.spawner.shutdown()
        # Shutdown IPC
        await self.ipc.stop()
        logger.info("System Alpha stopped.")
