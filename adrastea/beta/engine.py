import argparse
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ..activity_logger import ActivityLogger
from ..config import config
from ..directives import DirectiveWatcher
from ..ipc.channel import IPCClient
from ..ipc.protocol import Message, SignalType
from ..notifications.notifier import Notifier
from .delivery_strategist import DeliveryStrategist
from .discovery import GoalDiscovery
from .llm_consultant import LLMConsultant
from .mcp_client import MCPClient
from .triage import TriageEngine
from .tuner import HeuristicTuner

logger = logging.getLogger("Adrastea.Beta")


class BetaEngine:
    """Probabilistic Cognitive Engine for Adrastea."""

    def __init__(self, ipc_host: str = "127.0.0.1", ipc_port: int = 8765):
        self.ipc = IPCClient(host=ipc_host, port=ipc_port)
        self.llm = LLMConsultant()
        self.mcp = MCPClient()
        self.triage = TriageEngine(llm=self.llm)
        self.tuner = HeuristicTuner()
        self.discovery = GoalDiscovery(llm=self.llm)
        self.notifier = Notifier()
        self.strategist = DeliveryStrategist()
        self.watcher = DirectiveWatcher()
        self.activity_logger = ActivityLogger()

        self._running = False
        self._sleeping = False
        self._wake_event = asyncio.Event()
        self.sleep_interval = config.keepalive_sleep_seconds
        self._loop_task: Optional[asyncio.Task] = None
        self.last_telemetry: Dict[str, Any] = {}

        self._setup_ipc_handlers()

    def _setup_ipc_handlers(self) -> None:
        self.ipc.register_handler(SignalType.SIG_TELEMETRY, self._on_telemetry)
        self.ipc.register_handler(SignalType.SIG_STUCK, self._on_stuck)
        self.ipc.register_handler(SignalType.SIG_TASK_FAILED, self._on_task_failed)
        self.ipc.register_handler(SignalType.SIG_HEARTBEAT, self._on_heartbeat)
        self.ipc.register_handler(SignalType.SIG_SLEEP, self._on_sleep)
        self.ipc.register_handler(SignalType.SIG_WAKE, self._on_wake)

    async def _on_heartbeat(self, msg: Message) -> Message:
        logger.debug(f"Beta received heartbeat from {msg.sender}")
        return Message(
            signal=SignalType.SIG_HEARTBEAT,
            sender="Beta",
            payload={"status": "alive", "sleeping": self._sleeping, "timestamp": time.time()}
        )

    async def _on_sleep(self, msg: Message) -> None:
        duration = msg.payload.get("duration", self.sleep_interval)
        self.sleep_interval = float(duration)
        self._sleeping = True
        self._wake_event.clear()
        logger.info(f"Beta entered keep-alive sleep mode (interval: {self.sleep_interval}s). Listening and signaling remain active.")

    async def _on_wake(self, msg: Message) -> None:
        self._sleeping = False
        self._wake_event.set()
        logger.info("Beta received SIG_WAKE. Waking to active mode.")

    async def _on_telemetry(self, msg: Message) -> None:
        self.last_telemetry = msg.payload
        logger.debug(f"Received Alpha telemetry: Uptime={msg.payload.get('uptime_seconds')}s")

    async def _on_stuck(self, msg: Message) -> None:
        """Immediate high-priority triage when Alpha is stuck."""
        task_id = msg.payload.get("task_id", "unknown")
        logger.warning(f"ALPHA STUCK SIGNAL DETECTED for [{task_id}]")
        signals = self.triage.analyze_stuck_state(msg.payload)
        for sig in signals:
            logger.info(f"Beta dispatching corrective signal {sig.signal} to Alpha...")
            await self.ipc.send(sig)

        # Significant happening: Triage intervention!
        self.activity_logger.log_cycle(
            alpha_status=self.last_telemetry,
            beta_action=f"Autonomous Triage Intervention for stuck task [{task_id}]"
        )
        self.activity_logger.commit_and_push_significant_event(
            f"triaged and resolved stuck task [{task_id}]",
            min_cooldown_seconds=1800.0
        )

    async def _on_task_failed(self, msg: Message) -> None:
        logger.info(f"Task failed notification: {msg.payload.get('task_id')}")

    async def start(self) -> None:
        """Connect to Alpha IPC and start cognitive loop."""
        self._running = True
        logger.info("Initializing System Beta...")

        connected = await self.ipc.connect(retries=10, delay=1.0)
        if not connected:
            logger.error("Failed to connect to Alpha IPC Server. Exiting Beta.")
            return

        logger.info("System Beta connected to Alpha. Starting cognitive loop...")
        self._loop_task = asyncio.create_task(self._cognitive_loop())

    async def _cognitive_loop(self) -> None:
        """Main loop: Cycles through Idle/Wait, Directive Checking, Outreach with Backoff, and Optimization."""
        iteration = 0
        while self._running:
            try:
                iteration += 1
                logger.info(f"System Beta cognitive cycle #{iteration} (Observing & Idle)")

                # 1. Check for user directives from Luke (DIRECTIVES.txt or GitHub Issue comments)
                directive = self.watcher.check_directives()
                if directive:
                    logger.info(f"Directives received from Luke: '{directive}'")
                    self.strategist.reset_backoff_on_response()

                    # If sleeping, wake both Beta and Alpha
                    if self._sleeping:
                        self._sleeping = False
                        self._wake_event.set()
                        await self.ipc.send(Message(signal=SignalType.SIG_WAKE, sender="Beta"))

                    # Significant happening: User directive received!
                    safe_dir = directive.replace("'", "\\'")
                    cmd = f'python -c "print(\'Executed user directive: {safe_dir}\')"'
                    await self.ipc.send(
                        Message(
                            signal=SignalType.SIG_DISPATCH,
                            sender="Beta",
                            payload={
                                "task_id": f"user_directive_{int(time.time())}",
                                "command": cmd,
                                "priority": 100,
                                "metadata": {"user_directive": directive}
                            }
                        )
                    )

                    # Log locally and push significant event to GitHub immediately
                    self.activity_logger.log_cycle(
                        alpha_status=self.last_telemetry,
                        beta_action=f"Adopted and executed user directive: '{directive}'"
                    )
                    self.activity_logger.commit_and_push_significant_event(
                        f"adopted user directive '{directive[:40]}'",
                        bypass_cooldown=True
                    )

                # If in keep-alive sleep mode, sleep for long interval without heavy loops
                if self._sleeping:
                    logger.debug(f"Beta resting in keep-alive standby for {self.sleep_interval}s...")
                    try:
                        await asyncio.wait_for(self._wake_event.wait(), timeout=self.sleep_interval)
                        self._sleeping = False
                        self._wake_event.clear()
                        logger.info("Beta awakened from keep-alive sleep by event.")
                    except asyncio.TimeoutError:
                        pass
                    continue

                # 2. Heuristic Pathfinding Tuning
                if self.last_telemetry:
                    tune_msg = self.tuner.evaluate_telemetry(self.last_telemetry.get("telemetry", {}))
                    if tune_msg:
                        logger.info("Beta tuning Alpha's RL pathfinding weights...")
                        await self.ipc.send(tune_msg)

                # 3. Outreach & Inquiries with Adaptive Backoff (Logs locally without pushing to GitHub)
                if self.strategist.should_attempt_contact():
                    logger.info(f"Triggering outreach dispatch (Attempt #{self.strategist.contact_attempt_count + 1})...")
                    question = self.discovery.formulate_user_question(self.last_telemetry)
                    notify_res = self.notifier.notify_status(self.last_telemetry, custom_question=question)
                    self.strategist.mark_contact_attempted()

                    # Beta diagnoses delivery barriers using local Ollama model
                    channels = notify_res.get("channels", {})
                    adaptation = self.strategist.analyze_and_adapt(channels)
                    logger.info(f"Delivery diagnosis: {adaptation.get('barrier_summary')}")

                    # Record cycle locally in ACTIVITY_LOG.md (DO NOT PUSH - avoid relentless pounding)
                    self.activity_logger.log_cycle(
                        alpha_status=self.last_telemetry,
                        beta_action=f"Outreach Attempt #{self.strategist.contact_attempt_count} ({adaptation.get('best_working_channel', 'none')})",
                        outreach_results=channels,
                        pending_directive_prompt=question
                    )

                # 4. Periodic Discovery of novel diagnostic tasks
                if iteration % 6 == 0:
                    novel_task = self.discovery.discover_novel_task(self.last_telemetry)
                    if novel_task:
                        logger.info("Beta enqueuing novel discovered task for Alpha...")
                        await self.ipc.send(novel_task)

                # Idle sleep (can remain idle for days)
                await asyncio.sleep(config.beta_idle_cycle_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Beta cognitive loop: {e}", exc_info=True)
                await asyncio.sleep(config.beta_idle_cycle_seconds)

    async def stop(self) -> None:
        logger.info("Stopping System Beta...")
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
        await self.ipc.disconnect()
        logger.info("System Beta stopped.")


def main():
    parser = argparse.ArgumentParser(description="System Beta: Cognitive Reasoning Engine")
    parser.add_argument("--ipc-host", default="127.0.0.1", help="Alpha IPC host")
    parser.add_argument("--ipc-port", type=int, default=8765, help="Alpha IPC port")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

    engine = BetaEngine(ipc_host=args.ipc_host, ipc_port=args.ipc_port)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(engine.start())
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        loop.run_until_complete(engine.stop())
        loop.close()


if __name__ == "__main__":
    main()
