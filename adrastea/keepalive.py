import argparse
import asyncio
import logging
import sys
import time
from typing import Any, Dict, Optional

from .config import config
from .alpha.engine import AlphaEngine
from .tasks.builtins import get_default_scheduled_tasks
from .ipc.channel import IPCClient
from .ipc.protocol import Message, SignalType
from .directives import DirectiveWatcher

logger = logging.getLogger("Adrastea.KeepAlive")


class KeepAliveProcess:
    """Rudimentary Keep-Alive process coordinator for Adrastea.
    
    Lets the system sleep for long periods of time (saving CPU, memory, and API tokens)
    while continuously maintaining:
      1. Listening: Alpha IPC TCP server (127.0.0.1:8765) and IPC clients remain open.
      2. Signaling: Heartbeats (SIG_HEARTBEAT), wake events (SIG_WAKE), and dispatch
         signals (SIG_DISPATCH) are processed in real-time.
      3. Background processes: System Beta subprocess and async task runners remain
         supervised and running in the background.
    """

    def __init__(
        self,
        host: str = config.ipc_host,
        port: int = config.ipc_port,
        sleep_interval: float = config.keepalive_sleep_seconds,
        heartbeat_interval: float = config.keepalive_heartbeat_interval
    ):
        self.host = host
        self.port = port
        self.sleep_interval = sleep_interval
        self.heartbeat_interval = heartbeat_interval
        self.alpha: Optional[AlphaEngine] = None
        self.watcher = DirectiveWatcher()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self, sleep_interval: Optional[float] = None) -> None:
        """Start Alpha & Beta engines and transition into keep-alive sleep mode."""
        if sleep_interval is not None:
            self.sleep_interval = float(sleep_interval)

        self._running = True
        logger.info("==================================================")
        logger.info("   LAUNCHING ADRASTEA KEEP-ALIVE SUPERVISOR")
        logger.info(f"   Sleep Interval: {self.sleep_interval}s | Heartbeat: {self.heartbeat_interval}s")
        logger.info("==================================================")

        # 1. Initialize Alpha Engine
        self.alpha = AlphaEngine()
        for task in get_default_scheduled_tasks():
            self.alpha.scheduler.register(task)

        # 2. Start Alpha (which stabilizes and spawns Beta in background)
        await self.alpha.start()

        # 3. Enter keep-alive sleep mode
        await self.alpha.sleep(duration=self.sleep_interval)

        # 4. Launch keep-alive supervisory monitor
        self._monitor_task = asyncio.create_task(self._supervisory_loop())

    async def _supervisory_loop(self) -> None:
        """Keep-alive monitor loop running while the engines sleep."""
        logger.info("Keep-alive supervisor loop active. Listening, signaling, and background processes running.")
        last_heartbeat = time.time()

        while self._running and self.alpha and self.alpha._running:
            try:
                now = time.time()

                # 1. Check background Beta subprocess health
                if self.alpha.spawner.process is not None:
                    code = self.alpha.spawner.process.returncode
                    if code is not None:
                        logger.warning(f"Beta background process exited with code {code}! Reviving Beta...")
                        await self.alpha.spawner.spawn()

                # 2. Check for user directives in DIRECTIVES.txt
                directive = self.watcher.check_file_directive()
                if directive:
                    logger.info(f"Keep-alive supervisor detected directive: '{directive}'")
                    # Wake Alpha and dispatch directive
                    self.alpha.wake()
                    safe_dir = directive.replace("'", "\\'")
                    cmd = f'python -c "print(\'Executed user directive: {safe_dir}\')"'
                    self.alpha.scheduler.dispatch(
                        task_id=f"user_directive_{int(time.time())}",
                        command=cmd,
                        priority=100,
                        metadata={"user_directive": directive}
                    )

                # 3. Periodic heartbeat pulse to clients
                if now - last_heartbeat >= self.heartbeat_interval:
                    logger.debug("Keep-alive supervisor pulsing SIG_HEARTBEAT...")
                    await self.alpha.ipc.broadcast(
                        Message(
                            signal=SignalType.SIG_HEARTBEAT,
                            sender="KeepAliveSupervisor",
                            payload={
                                "status": "alive",
                                "sleeping": self.alpha._sleeping,
                                "sleep_interval": self.alpha.sleep_interval,
                                "timestamp": now
                            }
                        )
                    )
                    last_heartbeat = now

                # Sleep in short increments for the supervisor tick to remain responsive
                await asyncio.sleep(min(self.heartbeat_interval, 5.0))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in keep-alive supervisory loop: {e}", exc_info=True)
                await asyncio.sleep(5.0)

    async def stop(self) -> None:
        """Gracefully stop the keep-alive supervisor and child engines."""
        logger.info("Stopping Keep-Alive Supervisor...")
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        if self.alpha:
            await self.alpha.stop()
        logger.info("Keep-Alive Supervisor stopped.")

    # ------------------------------------------------------------------
    # Static IPC Client Helpers (for ping, remote sleep, remote wake)
    # ------------------------------------------------------------------

    @staticmethod
    async def ping(
        host: str = config.ipc_host,
        port: int = config.ipc_port,
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Send a SIG_HEARTBEAT ping to verify listening and signaling channels."""
        client = IPCClient(host=host, port=port)
        connected = await client.connect(retries=3, delay=0.5)
        if not connected:
            logger.error(f"Could not connect to Adrastea IPC at {host}:{port}")
            return None

        try:
            start_t = time.time()
            req = Message(
                signal=SignalType.SIG_HEARTBEAT,
                sender="KeepAliveClient",
                payload={"action": "ping"}
            )
            resp = await client.query(req, timeout=timeout)
            roundtrip_ms = round((time.time() - start_t) * 1000, 2)
            if resp:
                resp.payload["roundtrip_ms"] = roundtrip_ms
                return resp.payload
            return None
        finally:
            await client.disconnect()

    @staticmethod
    async def remote_sleep(
        duration: Optional[float] = None,
        host: str = config.ipc_host,
        port: int = config.ipc_port,
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Send SIG_SLEEP to put a running Adrastea instance to sleep."""
        client = IPCClient(host=host, port=port)
        connected = await client.connect(retries=3, delay=0.5)
        if not connected:
            return None
        try:
            req = Message(
                signal=SignalType.SIG_SLEEP,
                sender="KeepAliveClient",
                payload={"duration": duration or config.keepalive_sleep_seconds}
            )
            resp = await client.query(req, timeout=timeout)
            return resp.payload if resp else None
        finally:
            await client.disconnect()

    @staticmethod
    async def remote_wake(
        host: str = config.ipc_host,
        port: int = config.ipc_port,
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Send SIG_WAKE to wake a running Adrastea instance from sleep."""
        client = IPCClient(host=host, port=port)
        connected = await client.connect(retries=3, delay=0.5)
        if not connected:
            return None
        try:
            req = Message(
                signal=SignalType.SIG_WAKE,
                sender="KeepAliveClient",
                payload={"action": "wake"}
            )
            resp = await client.query(req, timeout=timeout)
            return resp.payload if resp else None
        finally:
            await client.disconnect()

    @staticmethod
    async def remote_status(
        host: str = config.ipc_host,
        port: int = config.ipc_port,
        timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """Query detailed status via SIG_QUERY_STATUS."""
        client = IPCClient(host=host, port=port)
        connected = await client.connect(retries=3, delay=0.5)
        if not connected:
            return None
        try:
            req = Message(
                signal=SignalType.SIG_QUERY_STATUS,
                sender="KeepAliveClient",
                payload={}
            )
            resp = await client.query(req, timeout=timeout)
            return resp.payload if resp else None
        finally:
            await client.disconnect()


async def run_keepalive_service(sleep_interval: float):
    """Run keep-alive supervisor service indefinitely."""
    supervisor = KeepAliveProcess(sleep_interval=sleep_interval)
    await supervisor.start()
    try:
        while supervisor._running:
            await asyncio.sleep(1.0)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received.")
    finally:
        await supervisor.stop()


def main():
    parser = argparse.ArgumentParser(description="Adrastea Keep-Alive Supervisor & Signaling Utility")
    parser.add_argument("--sleep-interval", type=float, default=config.keepalive_sleep_seconds, help="Sleep duration in seconds")
    parser.add_argument("--ping", action="store_true", help="Send heartbeat ping to running instance")
    parser.add_argument("--wake", action="store_true", help="Send wake signal to running instance")
    parser.add_argument("--sleep", type=float, nargs="?", const=config.keepalive_sleep_seconds, help="Send sleep signal to running instance")
    parser.add_argument("--status", action="store_true", help="Query status of running instance")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

    if args.ping:
        print(f"Pinging Adrastea at {config.ipc_host}:{config.ipc_port}...")
        res = asyncio.run(KeepAliveProcess.ping())
        if res:
            print(f"PONG: Adrastea is ALIVE. Roundtrip: {res.get('roundtrip_ms')}ms")
            print(f"State: {'SLEEPING (Keep-Alive)' if res.get('sleeping') else 'ACTIVE'}")
            print(f"Uptime: {res.get('uptime_seconds')}s | Beta Alive: {res.get('beta_alive')}")
        else:
            print("FAILED: Adrastea is not responding.")
            sys.exit(1)
    elif args.wake:
        print(f"Sending SIG_WAKE to Adrastea...")
        res = asyncio.run(KeepAliveProcess.remote_wake())
        print(f"Result: {res}")
    elif args.sleep is not None:
        print(f"Sending SIG_SLEEP ({args.sleep}s) to Adrastea...")
        res = asyncio.run(KeepAliveProcess.remote_sleep(duration=args.sleep))
        print(f"Result: {res}")
    elif args.status:
        print(f"Querying status from Adrastea...")
        res = asyncio.run(KeepAliveProcess.remote_status())
        if res:
            import json
            print(json.dumps(res, indent=2))
        else:
            print("FAILED: Could not retrieve status.")
            sys.exit(1)
    else:
        # Default: Run supervisor service
        asyncio.run(run_keepalive_service(args.sleep_interval))


if __name__ == "__main__":
    main()
