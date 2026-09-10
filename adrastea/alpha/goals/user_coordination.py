import logging
import sys
import time
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.UserCoordination")


class UserCoordinationGoal(BaseGoal):
    """Goal 2: Proactively communicate and coordinate with Luke as often as possible."""

    def __init__(self):
        super().__init__(
            goal_id="user_coordination",
            name="User Coordination & Continuous Outreach",
            description="Continuously monitors directives, engages the primary operator (Luke) across notification channels, and solicits strategic guidance.",
            enabled=True,
            weight=1.5,
            interval_seconds=getattr(config, "issue_loop_interval_seconds", 900.0),
            parameters={
                "urgency_level": "normal",  # normal, high, aggressive
                "require_response": False,
                "preferred_channels": ["github_verified_email", "desktop_balloon", "direct_email"],
                "inquiry_topic": "Operational priority and next milestones",
            },
        )

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = time.time()
        tasks: List[ScheduledTask] = []
        base_priority = int(25 * self.weight)

        # Dynamic load-adaptive interval adjustment (scaling up under heavy load)
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=None)
            ram = psutil.virtual_memory().percent
            base_interval = getattr(config, "issue_loop_interval_seconds", 900.0)
            if cpu >= 75.0 or ram >= 85.0:
                self.interval_seconds = max(base_interval * 4.0, 3600.0)
            elif cpu >= 40.0 or ram >= 70.0:
                self.interval_seconds = max(base_interval * 2.0, 1800.0)
            else:
                self.interval_seconds = base_interval
        except Exception:
            pass

        # 1. Directive Checking Task (Checking DIRECTIVES.txt and GitHub issues)
        cmd_directives = (
            f'"{sys.executable}" -c '
            '"from adrastea.directives import DirectiveWatcher; '
            'w = DirectiveWatcher(); '
            'd = w.check_directives(force=True); '
            'print(\'DIRECTIVES_POLL: DIRECTIVE_FOUND:\', d) if d else print(\'DIRECTIVES_POLL: No new directives\')"'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"coord_directives_poll_{int(now)}",
                command=cmd_directives,
                priority=base_priority + 10,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "intent": "Poll User Directives"},
            )
        )

        # 2. User Notification & Strategic Inquiry Task (Only if explicitly enabled and not waiting on response)
        if self.parameters.get("enable_periodic_outreach", False):
            cmd_outreach = (
                f'"{sys.executable}" -m adrastea.cli notify'
            )
            tasks.append(
                ScheduledTask(
                    task_id=f"coord_outreach_dispatch_{int(now)}",
                    command=cmd_outreach,
                    priority=base_priority,
                    interval_seconds=None,
                    metadata={"goal_id": self.goal_id, "intent": "User Outreach & Strategic Alignment"},
                )
            )

        self.mark_executed()
        return tasks
