import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("Adrastea.Alpha.Runner")


@dataclass
class TaskExecutionResult:
    task_id: str
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    interrupted: bool = False
    timestamp: float = field(default_factory=time.time)

    @property
    def is_success(self) -> bool:
        return self.exit_code == 0 and not self.interrupted


class LocalProgramRunner:
    """Executes local programs and scripts, managing processes and handling interruptions."""

    def __init__(self):
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.execution_history: List[TaskExecutionResult] = []

    async def execute(self, task_id: str, command: str, cwd: Optional[str] = None, timeout: float = 60.0) -> TaskExecutionResult:
        """Execute a command locally with timeout and signal interrupt support."""
        start_time = time.time()
        interrupted = False
        stdout_str = ""
        stderr_str = ""
        exit_code = -1

        logger.info(f"Starting execution for [{task_id}]: {command}")
        try:
            # Using shell=True for flexible command / script execution on Windows
            run_env = os.environ.copy()
            run_env["PYTHONUTF8"] = "1"
            run_env["PYTHONIOENCODING"] = "utf-8"
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=run_env,
            )
            self.active_processes[task_id] = proc

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
                stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
                exit_code = proc.returncode if proc.returncode is not None else 0
            except asyncio.TimeoutError:
                logger.warning(f"Task [{task_id}] timed out after {timeout}s. Terminating...")
                proc.kill()
                await proc.wait()
                stderr_str = f"Task timed out after {timeout} seconds."
                exit_code = -99
            except asyncio.CancelledError:
                logger.warning(f"Task [{task_id}] execution cancelled. Terminating...")
                interrupted = True
                proc.kill()
                await proc.wait()
                exit_code = -98
                raise

        except Exception as e:
            logger.error(f"Task [{task_id}] failed to start or execute: {e}")
            stderr_str = str(e)
            exit_code = -1
        finally:
            self.active_processes.pop(task_id, None)

        duration = time.time() - start_time
        result = TaskExecutionResult(
            task_id=task_id,
            command=command,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            duration_seconds=round(duration, 3),
            interrupted=interrupted
        )
        self.execution_history.append(result)
        # Keep history capped
        if len(self.execution_history) > 200:
            self.execution_history = self.execution_history[-200:]

        logger.info(f"Task [{task_id}] finished in {result.duration_seconds}s with exit code {exit_code}")
        return result

    async def interrupt(self, task_id: str) -> bool:
        """Interrupt / kill an in-flight task by ID."""
        proc = self.active_processes.get(task_id)
        if proc and proc.returncode is None:
            logger.warning(f"Interrupting in-flight task [{task_id}]")
            try:
                proc.kill()
                await proc.wait()
                return True
            except Exception as e:
                logger.error(f"Failed to kill task [{task_id}]: {e}")
                return False
        return False

    def list_active_tasks(self) -> List[str]:
        return list(self.active_processes.keys())
