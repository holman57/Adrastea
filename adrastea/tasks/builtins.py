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

    # 4. Daily Cultural Zeitgeist Radar Task (Runs daily / every 24 hours)
    cmd_zeitgeist = (
        f'"{sys.executable}" -m market_research.inquiry.zeitgeist_radar --sync'
    )
    tasks.append(
        ScheduledTask(
            task_id="market_research_daily_zeitgeist",
            command=cmd_zeitgeist,
            interval_seconds=86400.0,  # 24 hours (everyday)
            priority=25,
            metadata={
                "description": "Daily synchronization of cultural zeitgeist radar issue on holman57/market-research",
                "target_repo": "market-research",
            }
        )
    )

    # 5. Target Repositories Loop Task (Runs immediately on startup, then every 300 seconds)
    cmd_repo_loop = (
        f'"{sys.executable}" -m adrastea.alpha.solved_problems loop'
    )
    tasks.append(
        ScheduledTask(
            task_id="target_repositories_loop",
            command=cmd_repo_loop,
            interval_seconds=300.0,
            priority=35,
            metadata={"description": "Continuously loops through all target repositories, evaluating open issues and readiness"}
        )
    )

    return tasks
