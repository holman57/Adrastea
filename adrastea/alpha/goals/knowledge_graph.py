import logging
import sys
import time
from typing import Any, Dict, List, Optional

from ...config import config
from ..scheduler import ScheduledTask
from .base import BaseGoal

logger = logging.getLogger("Adrastea.Alpha.Goals.KnowledgeGraph")


class KnowledgeGraphMemoryGoal(BaseGoal):
    """Goal 4: Maintain graph knowledge base and manage short-, medium-, and long-term memories."""

    def __init__(self):
        super().__init__(
            goal_id="knowledge_graph_memory",
            name="Graph Knowledge Base & Multi-Tier Memory Management",
            description="Maintains Neo4j and embedded SQLite graph database, executes memory decay and consolidation, and enriches semantic ontology.",
            enabled=True,
            weight=1.3,
            interval_seconds=180.0,
            parameters={
                "consolidation_decay_rate": 0.85,
                "sync_neo4j": True,
                "auto_promote_frequent_nodes": True,
                "short_term_ttl_seconds": 7200.0,
            },
        )

    def generate_tasks(self, context: Optional[Dict[str, Any]] = None) -> List[ScheduledTask]:
        now = time.time()
        tasks: List[ScheduledTask] = []
        base_priority = int(18 * self.weight)

        decay_rate = self.parameters.get("consolidation_decay_rate", 0.85)

        # Task 1: Autonomous Memory Consolidation & Pruning Task
        cmd_consolidate = (
            f'"{sys.executable}" -m adrastea.knowledge.memory_manager consolidate {decay_rate}'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"kg_consolidate_{int(now)}",
                command=cmd_consolidate,
                priority=base_priority + 5,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "intent": "Memory Decay & Consolidation Cycle"},
            )
        )

        # Task 2: Graph Database Health & Neo4j Verification Task
        cmd_health = (
            f'"{sys.executable}" -m adrastea.knowledge.memory_manager health'
        )
        tasks.append(
            ScheduledTask(
                task_id=f"kg_health_check_{int(now)}",
                command=cmd_health,
                priority=base_priority,
                interval_seconds=None,
                metadata={"goal_id": self.goal_id, "intent": "Knowledge Graph Integrity & Topology Scan"},
            )
        )

        self.mark_executed()
        return tasks
