import argparse
import asyncio
import logging
import time
from typing import Any, Dict, Optional

from ..config import config
from ..ipc.channel import IPCClient
from ..ipc.protocol import Message, SignalType
from ..notifications.notifier import Notifier
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

        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self.last_telemetry: Dict[str, Any] = {}
        self.last_notification_time = 0.0

        self._setup_ipc_handlers()

    def _setup_ipc_handlers(self) -> None:
        self.ipc.register_handler(SignalType.SIG_TELEMETRY, self._on_telemetry)
        self.ipc.register_handler(SignalType.SIG_STUCK, self._on_stuck)
        self.ipc.register_handler(SignalType.SIG_TASK_FAILED, self._on_task_failed)

    async def _on_telemetry(self, msg: Message) -> None:
        self.last_telemetry = msg.payload
        logger.debug(f"Received Alpha telemetry: Uptime={msg.payload.get('uptime_seconds')}s")

    async def _on_stuck(self, msg: Message) -> None:
        """Immediate high-priority triage when Alpha is stuck."""
        logger.warning(f"ALPHA STUCK SIGNAL DETECTED: {msg.payload}")
        signals = self.triage.analyze_stuck_state(msg.payload)
        for sig in signals:
            logger.info(f"Beta dispatching corrective signal {sig.signal} to Alpha...")
            await self.ipc.send(sig)

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
        """Main loop: Cycles through Idle/Wait, Optimize, and Discover modes."""
        iteration = 0
        while self._running:
            try:
                iteration += 1
                logger.info(f"System Beta cognitive cycle #{iteration} (Idle/Wait mode)")

                # Mode 1: Optimize Alpha's Workflow & Pathfinding Weights
                if self.last_telemetry:
                    tune_msg = self.tuner.evaluate_telemetry(self.last_telemetry.get("telemetry", {}))
                    if tune_msg:
                        logger.info("Beta tuning Alpha's RL pathfinding weights...")
                        await self.ipc.send(tune_msg)

                # Mode 2: Notification & User Direction Request
                # Send immediate first notification on stabilization, then periodically
                now = time.time()
                time_since_last = now - self.last_notification_time
                notification_interval_sec = config.notification_interval_minutes * 60

                if self.last_notification_time == 0.0 or time_since_last >= notification_interval_sec:
                    logger.info("Triggering user notification & direction prompt...")
                    question = self.discovery.formulate_user_question(self.last_telemetry)
                    self.notifier.notify_status(self.last_telemetry, custom_question=question)
                    self.last_notification_time = now

                # Mode 3: Goal Discovery
                if iteration % 4 == 0:
                    novel_task = self.discovery.discover_novel_task(self.last_telemetry)
                    if novel_task:
                        logger.info("Beta enqueuing novel discovered task for Alpha...")
                        await self.ipc.send(novel_task)

                # Wait in idle state (can remain idle for days)
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
