import asyncio
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger("Adrastea.Alpha.Spawner")


class BetaSpawner:
    """Spawns and supervises System Beta as an independent process once Alpha stabilizes."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.process: Optional[asyncio.subprocess.Process] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False

    async def spawn(self) -> bool:
        """Spawn the Beta engine process."""
        if self.process and self.process.returncode is None:
            logger.warning("Beta is already running.")
            return True

        logger.info(f"Spawning System Beta connecting to IPC {self.host}:{self.port}...")
        try:
            cmd = [
                sys.executable,
                "-m", "adrastea.beta.engine",
                "--ipc-host", self.host,
                "--ipc-port", str(self.port)
            ]
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            self._running = True
            self._monitor_task = asyncio.create_task(self._supervise_beta())
            logger.info(f"System Beta spawned successfully (PID: {self.process.pid}).")
            return True
        except Exception as e:
            logger.error(f"Failed to spawn System Beta: {e}")
            return False

    async def _supervise_beta(self) -> None:
        """Read stdout/stderr from Beta and log them; handle restarts if Beta crashes."""
        if not self.process:
            return

        async def read_stream(stream, prefix):
            while self._running and stream:
                line = await stream.readline()
                if not line:
                    break
                logger.info(f"[{prefix}] {line.decode('utf-8', errors='replace').rstrip()}")

        try:
            await asyncio.gather(
                read_stream(self.process.stdout, "BETA"),
                read_stream(self.process.stderr, "BETA_ERR")
            )
            exit_code = await self.process.wait()
            logger.warning(f"Beta process exited with code {exit_code}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Beta supervisor: {e}")

    async def shutdown(self) -> None:
        """Gracefully terminate Beta."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        if self.process and self.process.returncode is None:
            logger.info("Terminating Beta process...")
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                self.process.kill()
                await self.process.wait()
            logger.info("Beta process terminated.")
