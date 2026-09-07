import asyncio
import logging
import sys
import time
from typing import Any, Dict, Optional

from ..config import config
from ..ipc.channel import IPCServer
from ..ipc.protocol import Message, SignalType
from ..knowledge.memory_manager import MemoryManager
from .goals.manager import GoalManager
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
        self.memory = MemoryManager()
        self.goal_manager = GoalManager()

        self._running = False
        self._sleeping = False
        self._wake_event = asyncio.Event()
        self.sleep_interval = config.keepalive_sleep_seconds
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
        self.ipc.register_handler(SignalType.SIG_TUNE_GOALS, self._on_tune_goals)
        self.ipc.register_handler(SignalType.SIG_QUERY_GOALS, self._on_query_goals)
        self.ipc.register_handler(SignalType.SIG_QUERY_STATUS, self._on_query_status)
        self.ipc.register_handler(SignalType.SIG_SHUTDOWN, self._on_shutdown_signal)
        self.ipc.register_handler(SignalType.SIG_HEARTBEAT, self._on_heartbeat)
        self.ipc.register_handler(SignalType.SIG_SLEEP, self._on_sleep)
        self.ipc.register_handler(SignalType.SIG_WAKE, self._on_wake)
        self.ipc.register_handler(SignalType.SIG_CONVERSATION, self._on_conversation)

    async def _on_heartbeat(self, msg: Message) -> Message:
        uptime = time.time() - self.start_time if self.start_time else 0
        beta_alive = self.spawner.process is not None and self.spawner.process.returncode is None
        logger.debug(f"Received SIG_HEARTBEAT from {msg.sender}")
        return Message(
            signal=SignalType.SIG_HEARTBEAT,
            sender="Alpha",
            payload={
                "status": "alive",
                "sleeping": self._sleeping,
                "sleep_interval": self.sleep_interval,
                "uptime_seconds": round(uptime, 2),
                "beta_alive": beta_alive,
                "active_tasks": self.runner.list_active_tasks(),
                "timestamp": time.time()
            }
        )

    async def _on_sleep(self, msg: Message) -> Message:
        duration = msg.payload.get("duration", self.sleep_interval)
        logger.info(f"Received SIG_SLEEP from {msg.sender}. Entering sleep for {duration}s...")
        await self.sleep(duration=float(duration))
        return Message(
            signal=SignalType.SIG_SLEEP,
            sender="Alpha",
            payload={"action": "sleeping", "duration": self.sleep_interval}
        )

    async def _on_wake(self, msg: Message) -> Message:
        logger.info(f"Received SIG_WAKE from {msg.sender}. Waking Alpha...")
        self.wake()
        return Message(
            signal=SignalType.SIG_WAKE,
            sender="Alpha",
            payload={"action": "awake"}
        )

    async def _on_conversation(self, msg: Message) -> Message:
        """Handle conversational input from Speech Flow, decide response/action, and return speech payload."""
        text = msg.payload.get("text", "").strip()
        word_buffer = msg.payload.get("words", [])
        logger.info(f"Speech Flow input received: '{text}' ({len(word_buffer)} words)")

        text_lower = text.lower()
        response_text = ""
        action_taken = "none"

        # 1. Direct Voice Command Interpretations
        if any(w in text_lower for w in ["status", "system status", "how are you", "what is your status"]):
            st = self.get_status()
            state_str = "sleeping in keep-alive mode" if st["sleeping"] else "active"
            response_text = (
                f"Adrastea is currently {state_str}. "
                f"Uptime is {int(st['uptime_seconds'])} seconds, with {len(st['active_tasks'])} active tasks "
                f"and {st['scheduled_tasks_count']} scheduled tasks registered."
            )
            action_taken = "status_report"

        elif any(w in text_lower for w in ["wake up", "wake", "resume", "start working"]):
            self.wake()
            response_text = "System Alpha has awakened from keep-alive mode. Task scheduler and deterministic loop are active."
            action_taken = "system_wake"

        elif any(w in text_lower for w in ["go to sleep", "sleep", "standby", "rest"]):
            await self.sleep()
            response_text = f"Adrastea entering keep-alive sleep for {int(self.sleep_interval)} seconds. Listening and signaling remain active."
            action_taken = "system_sleep"

        elif any(w in text_lower for w in ["health check", "diagnostics", "system health", "cpu", "memory", "ram"]):
            cmd_health = f'"{sys.executable}" -c "import psutil; print(f\'SYSTEM_HEALTH: CPU={{psutil.cpu_percent()}}%, RAM={{psutil.virtual_memory().percent}}%\')"'
            task_id = f"voice_diag_{int(time.time())}"
            self.scheduler.dispatch(task_id, cmd_health, priority=100)
            if self._sleeping:
                self.wake()
            response_text = "Dispatched an immediate system health and resource diagnostic."
            action_taken = "dispatch_diagnostic"

        else:
            # 2. General Conversational Reasoning (Ollama / LLM)
            uptime_s = int(time.time() - self.start_time if self.start_time else 0)
            status_summary = f"State: {'Sleeping' if self._sleeping else 'Active'}, Uptime: {uptime_s}s, Tasks: {len(self.scheduler.tasks)}"
            prompt = (
                f"User spoken input from Speech Flow: '{text}'\n"
                f"Adrastea system context: {status_summary}\n"
                f"Respond with a clear, conversational answer (1 to 2 sentences) suitable for text-to-speech audio playback."
            )
            llm_resp = self.local_llm.generate(prompt, system="You are Adrastea, an autonomous paired AI orchestrator. Speak concisely and clearly.")
            if llm_resp:
                response_text = llm_resp.strip()
            else:
                response_text = f"Processed voice input: {text}. Adrastea operational."
            action_taken = "conversational_dialogue"

        return Message(
            signal=SignalType.SIG_CONVERSATION,
            sender="Adrastea",
            payload={
                "reply_to": msg.message_id,
                "text": response_text,
                "action": action_taken,
                "system_status": {
                    "sleeping": self._sleeping,
                    "uptime_seconds": round(time.time() - self.start_time if self.start_time else 0, 1),
                },
                "timestamp": time.time()
            }
        )

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
        logger.info(f"Received SIG_DISPATCH from {msg.sender}: [{task_id}] -> {command}")
        if task_id and command:
            self.scheduler.dispatch(task_id, command, priority=priority, metadata=msg.payload.get("metadata", {}))
            # If sleeping, wake Alpha to execute the newly dispatched task immediately
            if self._sleeping:
                logger.info(f"Dispatched task [{task_id}] waking Alpha from keep-alive sleep...")
                self.wake()
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

    async def _on_tune_goals(self, msg: Message) -> Optional[Message]:
        goal_id = msg.payload.get("goal_id")
        updates = msg.payload.get("updates", msg.payload)
        logger.info(f"Received SIG_TUNE_GOALS from Beta for [{goal_id}]: {updates}")
        if goal_id:
            success = self.goal_manager.tune_goal(goal_id, updates)
            return Message(
                signal=SignalType.SIG_GOALS_STATUS,
                sender="Alpha",
                payload={
                    "action": "goal_tuned",
                    "goal_id": goal_id,
                    "success": success,
                    "status": self.goal_manager.get_goals_status()
                }
            )
        return None

    async def _on_query_goals(self, msg: Message) -> Message:
        return Message(
            signal=SignalType.SIG_GOALS_STATUS,
            sender="Alpha",
            payload=self.goal_manager.get_goals_status()
        )

    async def _on_query_status(self, msg: Message) -> Message:
        return Message(
            signal=SignalType.SIG_TELEMETRY,
            sender="Alpha",
            payload=self.get_status()
        )

    async def _on_shutdown_signal(self, msg: Message) -> None:
        logger.info("Received SIG_SHUTDOWN from Beta.")
        await self.stop()

    async def sleep(self, duration: Optional[float] = None) -> None:
        """Put Alpha and Beta into low-overhead keepalive sleep mode."""
        if duration is not None:
            self.sleep_interval = float(duration)
        self._sleeping = True
        self._wake_event.clear()
        logger.info(f"System Alpha entering keep-alive sleep mode (interval: {self.sleep_interval}s). Listening and signaling remain active.")
        # Broadcast sleep signal to Beta so it enters sleep mode as well
        await self.ipc.broadcast(
            Message(
                signal=SignalType.SIG_SLEEP,
                sender="Alpha",
                payload={"duration": self.sleep_interval}
            )
        )

    def wake(self) -> None:
        """Wake Alpha and Beta from sleep mode immediately."""
        self._sleeping = False
        self._wake_event.set()
        logger.info("System Alpha woken from sleep mode. Resuming standard cycles.")
        # Broadcast wake signal to Beta
        if self.ipc._running:
            asyncio.create_task(
                self.ipc.broadcast(
                    Message(
                        signal=SignalType.SIG_WAKE,
                        sender="Alpha",
                        payload={"status": "awake"}
                    )
                )
            )

    def get_status(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time if self.start_time else 0
        return {
            "uptime_seconds": round(uptime, 2),
            "running": self._running,
            "sleeping": self._sleeping,
            "sleep_interval": self.sleep_interval,
            "beta_spawned": self._beta_spawned,
            "active_tasks": self.runner.list_active_tasks(),
            "scheduled_tasks_count": len(self.scheduler.tasks),
            "telemetry": self.planner.get_summary_telemetry(),
            "local_llm_online": self.local_llm.is_available(),
            "goals": self.goal_manager.get_goals_status(),
            "knowledge_graph": self.memory.get_summary()
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
                if self._sleeping:
                    try:
                        # Sleep for long period of time, waking immediately if signaled
                        await asyncio.wait_for(self._wake_event.wait(), timeout=self.sleep_interval)
                        # An event woke Alpha up!
                        self._sleeping = False
                        self._wake_event.clear()
                        logger.info("Alpha awakened from keep-alive sleep by event.")
                    except asyncio.TimeoutError:
                        # Keep-alive sleep interval elapsed; pulse keep-alive heartbeat
                        logger.debug("Alpha keep-alive interval elapsed. Emitting keep-alive pulse...")
                        await self.ipc.broadcast(
                            Message(
                                signal=SignalType.SIG_HEARTBEAT,
                                sender="Alpha",
                                payload=self.get_status()
                            )
                        )
                        continue

                # 1. Synthesize tasks from autonomous goals
                new_goal_tasks = self.goal_manager.generate_due_tasks()
                for gtask in new_goal_tasks:
                    self.scheduler.register(gtask)

                # 2. Retrieve due tasks ordered by RL planner
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
        """Execute a scheduled task, evaluate RL score, record to memory, and report to Beta."""
        task.mark_executed()
        result: TaskExecutionResult = await self.runner.execute(task.task_id, task.command)

        # RL Planner evaluates outcome and computes reward
        reward = self.planner.record_outcome(result)

        # Ingest execution into Knowledge Graph Memory
        try:
            self.memory.record_task_execution(
                task_id=task.task_id,
                command=task.command,
                result={
                    "exit_code": result.exit_code,
                    "duration": result.duration_seconds,
                    "stdout_sample": result.stdout[:200],
                    "stderr_sample": result.stderr[:200],
                }
            )
        except Exception as me:
            logger.warning(f"Failed to record task execution to memory: {me}")

        # Update Goal metrics if task originated from a goal
        goal_id = task.metadata.get("goal_id")
        if goal_id:
            self.goal_manager.record_task_outcome(goal_id, result.is_success)

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
