import sys
from typing import List
from ..alpha.scheduler import ScheduledTask


def get_default_scheduled_tasks() -> List[ScheduledTask]:
    """Returns the standard default tasks for System Alpha to register on startup."""
    tasks = []

    # 1. System Telemetry Task (Every 60 seconds)
    cmd_health = (
        f'"{sys.executable}" -c '
        '"import psutil; print(f\'SYSTEM_HEALTH: CPU={psutil.cpu_percent()}%, RAM={psutil.virtual_memory().percent}%\')"'
    )
    tasks.append(
        ScheduledTask(
            task_id="system_health_check",
            command=cmd_health,
            interval_seconds=60.0,
            priority=10,
            metadata={"description": "Monitors CPU and RAM utilization"}
        )
    )

    # 2. Local LLM Health Check (Every 120 seconds)
    cmd_llm = (
        f'"{sys.executable}" -c '
        '"import urllib.request, json; '
        'req = urllib.request.Request(\'http://127.0.0.1:11434/api/tags\'); '
        'res = urllib.request.urlopen(req, timeout=5); '
        'data = json.loads(res.read().decode()); '
        'print(f\'OLLAMA_STATUS: {len(data.get(\"models\", []))} models available\')"'
    )
    tasks.append(
        ScheduledTask(
            task_id="ollama_health_check",
            command=cmd_llm,
            interval_seconds=120.0,
            priority=15,
            metadata={"description": "Verifies local Ollama model endpoint"}
        )
    )

    # 3. Notification Dispatch Task (Runs once immediately after startup, then every hour)
    cmd_notify = (
        f'"{sys.executable}" -m adrastea.cli notify'
    )
    tasks.append(
        ScheduledTask(
            task_id="user_notification_dispatch",
            command=cmd_notify,
            interval_seconds=3600.0,  # 1 hour
            priority=30,
            metadata={"description": "Dispatches status update and direction inquiry to user via Email and SMS"}
        )
    )

    return tasks
