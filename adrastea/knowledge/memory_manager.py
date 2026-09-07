import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from ..config import config
from .graph_store import GraphStore, create_graph_store
from .models import GraphNode, GraphRelationship, MemoryTier

logger = logging.getLogger("Adrastea.Knowledge.MemoryManager")


class MemoryManager:
    """Multi-tiered memory management engine establishing a graph knowledge base for Adrastea."""

    def __init__(self, store: Optional[GraphStore] = None):
        self.store = store or create_graph_store(
            db_path=config.knowledge_db_path,
            neo4j_uri=config.neo4j_uri,
            neo4j_user=config.neo4j_user,
            neo4j_password=config.neo4j_password,
        )
        self._ensure_root_ontology()

    def _ensure_root_ontology(self) -> None:
        """Seed foundational system nodes and identity in long-term memory."""
        # 1. System Self Node
        if not self.store.get_node("adrastea_system"):
            self.store.upsert_node(
                GraphNode(
                    id="adrastea_system",
                    label="System",
                    tier=MemoryTier.LONG_TERM,
                    properties={
                        "name": "Adrastea",
                        "description": "Autonomous paired AI execution orchestrator",
                        "engines": ["Alpha (Deterministic Execution)", "Beta (Cognitive Strategist)"],
                        "started_at": time.time(),
                    },
                    decay_score=1.0,
                )
            )

        # 2. User Node (Luke)
        if not self.store.get_node("user_luke"):
            self.store.upsert_node(
                GraphNode(
                    id="user_luke",
                    label="User",
                    tier=MemoryTier.LONG_TERM,
                    properties={
                        "name": "Luke Holman",
                        "handle": "holman57",
                        "email": config.target_email or "Holman57@gmail.com",
                        "phone": config.target_phone or "214-733-0312",
                        "role": "Primary Operator / Decision Authority",
                    },
                    decay_score=1.0,
                )
            )
            self.store.upsert_relationship(
                GraphRelationship(
                    source_id="adrastea_system",
                    target_id="user_luke",
                    rel_type="COORDINATES_WITH",
                    weight=1.0,
                )
            )

    # -------------------------------------------------------------------------
    # Tiered Storage Operations
    # -------------------------------------------------------------------------

    def store_short_term(
        self,
        label: str,
        properties: Dict[str, Any],
        node_id: Optional[str] = None,
        ttl_seconds: float = 3600.0,
    ) -> str:
        """Store transient episodic memory (execution log, immediate telemetry, conversation trace)."""
        nid = node_id or f"stm_{label.lower()}_{uuid.uuid4().hex[:8]}"
        now = time.time()
        node = GraphNode(
            id=nid,
            label=label,
            tier=MemoryTier.SHORT_TERM,
            properties=properties,
            created_at=now,
            last_accessed=now,
            decay_score=1.0,
            expires_at=now + ttl_seconds,
        )
        self.store.upsert_node(node)
        return nid

    def store_medium_term(
        self,
        label: str,
        properties: Dict[str, Any],
        node_id: Optional[str] = None,
        ttl_seconds: float = 86400.0 * 7,
    ) -> str:
        """Store tactical memory (weekly heuristics, failure patterns, task performance summaries)."""
        nid = node_id or f"mtm_{label.lower()}_{uuid.uuid4().hex[:8]}"
        now = time.time()
        node = GraphNode(
            id=nid,
            label=label,
            tier=MemoryTier.MEDIUM_TERM,
            properties=properties,
            created_at=now,
            last_accessed=now,
            decay_score=1.0,
            expires_at=now + ttl_seconds,
        )
        self.store.upsert_node(node)
        return nid

    def store_long_term(
        self,
        label: str,
        properties: Dict[str, Any],
        node_id: Optional[str] = None,
    ) -> str:
        """Store permanent semantic knowledge (architecture concepts, core goals, user directives)."""
        nid = node_id or f"ltm_{label.lower()}_{uuid.uuid4().hex[:8]}"
        now = time.time()
        node = GraphNode(
            id=nid,
            label=label,
            tier=MemoryTier.LONG_TERM,
            properties=properties,
            created_at=now,
            last_accessed=now,
            decay_score=1.0,
            expires_at=None,
        )
        self.store.upsert_node(node)
        return nid

    def link_memories(
        self,
        source_id: str,
        target_id: str,
        rel_type: str,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Create a graph relationship linking two memories or entities."""
        rel = GraphRelationship(
            source_id=source_id,
            target_id=target_id,
            rel_type=rel_type,
            properties=properties or {},
            weight=weight,
        )
        self.store.upsert_relationship(rel)

    # -------------------------------------------------------------------------
    # Domain-Specific Memory Ingestion
    # -------------------------------------------------------------------------

    def record_task_execution(self, task_id: str, command: str, result: Dict[str, Any]) -> str:
        """Ingests task execution trace into short-term memory, linking to failure patterns if broken."""
        is_success = result.get("exit_code") == 0
        nid = self.store_short_term(
            label="TaskTrace",
            properties={
                "task_id": task_id,
                "command": command,
                "exit_code": result.get("exit_code"),
                "duration": result.get("duration"),
                "success": is_success,
                "stdout_sample": result.get("stdout_sample", "")[:200],
                "stderr_sample": result.get("stderr_sample", "")[:200],
            },
            ttl_seconds=7200.0,
        )
        self.link_memories(source_id="adrastea_system", target_id=nid, rel_type="EXECUTED_TRACE")

        # If failed, link to or establish a Medium-Term FailurePattern
        if not is_success:
            pattern_id = f"pattern_fail_{task_id}"
            existing = self.store.get_node(pattern_id)
            if existing:
                count = existing.properties.get("consecutive_failures", 1) + 1
                existing.properties["consecutive_failures"] = count
                existing.properties["last_error"] = result.get("stderr_sample", "")
                existing.touch()
                self.store.upsert_node(existing)
            else:
                self.store_medium_term(
                    label="FailurePattern",
                    properties={
                        "task_id": task_id,
                        "consecutive_failures": 1,
                        "last_error": result.get("stderr_sample", ""),
                    },
                    node_id=pattern_id,
                )
            self.link_memories(source_id=nid, target_id=pattern_id, rel_type="EXHIBITS_PATTERN")

        return nid

    def record_user_directive(
        self,
        directive_text: str,
        source: str = "DIRECTIVES.txt",
        target_goal: Optional[str] = None,
        issue_number: Optional[int] = None,
    ) -> str:
        """Stores a directive from Luke into long-term memory and links to user and goal."""
        props: Dict[str, Any] = {
            "directive": directive_text,
            "source": source,
            "timestamp": time.time(),
            "status": "ADOPTED",
        }
        if target_goal:
            props["target_goal"] = target_goal
        if issue_number:
            props["issue_number"] = issue_number

        nid = self.store_long_term(
            label="UserDirective",
            properties=props,
        )
        self.link_memories(source_id="user_luke", target_id=nid, rel_type="ISSUED_DIRECTIVE")
        self.link_memories(source_id="adrastea_system", target_id=nid, rel_type="ACTS_UPON")
        if target_goal:
            self.link_memories(source_id=nid, target_id=f"goal_{target_goal}", rel_type="STEERS_GOAL")
        return nid

    def record_companion_project(self, repo_name: str, status: Dict[str, Any]) -> str:
        """Stores or updates status of companion AI-managed projects."""
        nid = f"project_{repo_name.lower().replace('-', '_')}"
        existing = self.store.get_node(nid)
        if existing:
            existing.properties.update(status)
            existing.touch()
            self.store.upsert_node(existing)
        else:
            self.store_long_term(
                label="CompanionProject",
                properties={"repo_name": repo_name, **status},
                node_id=nid,
            )
            self.link_memories(source_id="adrastea_system", target_id=nid, rel_type="MANAGES_PROJECT")
        return nid

    # -------------------------------------------------------------------------
    # Memory Consolidation & Decay
    # -------------------------------------------------------------------------

    def consolidate_memories(self, decay_rate: float = 0.85) -> Dict[str, Any]:
        """Runs memory consolidation:
        1. Promotes heavily accessed short-term traces into medium-term insights.
        2. Promotes recurring medium-term patterns with fixes into long-term solutions.
        3. Decays and prunes expired short-term nodes.
        """
        now = time.time()
        promoted_count = 0

        # Step 1: Scan short-term nodes for high engagement or repeated patterns
        st_nodes = self.store.query_nodes(tier=MemoryTier.SHORT_TERM, limit=100)
        for node in st_nodes:
            # If a short-term node has been accessed multiple times, promote it to medium-term
            if node.access_count >= 3 or node.decay_score >= 0.95 and (now - node.created_at > 600):
                node.tier = MemoryTier.MEDIUM_TERM
                node.expires_at = now + (86400.0 * 7)  # 7 days
                self.store.upsert_node(node)
                promoted_count += 1
                logger.info(f"Memory Consolidation: Promoted {node.id} to MEDIUM_TERM memory.")

        # Step 2: Decay and prune expired short-term memories
        pruned_short = self.store.decay_and_prune(
            tier=MemoryTier.SHORT_TERM,
            ttl_seconds=7200.0,  # 2 hours default TTL
            decay_rate=decay_rate,
        )

        # Step 3: Decay medium-term memories
        pruned_medium = self.store.decay_and_prune(
            tier=MemoryTier.MEDIUM_TERM,
            ttl_seconds=86400.0 * 14,  # 14 days
            decay_rate=0.95,
        )

        return {
            "promoted_to_medium": promoted_count,
            "pruned_short_term": pruned_short,
            "pruned_medium_term": pruned_medium,
            "timestamp": now,
        }

    def recall_context(self, search_term: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Recalls relevant memory nodes across all tiers matching keywords."""
        nodes = self.store.query_nodes(search=search_term, limit=limit)
        results = []
        for n in nodes:
            rels = self.store.get_relationships(n.id)
            results.append({
                "node": n.to_dict(),
                "relationships": [r.to_dict() for r in rels],
            })
        return results

    def get_summary(self) -> Dict[str, Any]:
        """Return high-level telemetry and node distribution of the knowledge graph."""
        return self.store.get_graph_stats()
