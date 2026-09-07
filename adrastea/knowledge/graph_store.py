import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .models import GraphNode, GraphRelationship, MemoryTier

logger = logging.getLogger("Adrastea.Knowledge.GraphStore")


class GraphStore(ABC):
    """Abstract interface for knowledge graph backends (Neo4j, SQLite, etc.)."""

    @abstractmethod
    def upsert_node(self, node: GraphNode) -> None:
        pass

    @abstractmethod
    def get_node(self, node_id: str) -> Optional[GraphNode]:
        pass

    @abstractmethod
    def delete_node(self, node_id: str) -> bool:
        pass

    @abstractmethod
    def upsert_relationship(self, rel: GraphRelationship) -> None:
        pass

    @abstractmethod
    def get_relationships(self, node_id: str, direction: str = "both") -> List[GraphRelationship]:
        pass

    @abstractmethod
    def query_nodes(
        self,
        label: Optional[str] = None,
        tier: Optional[MemoryTier] = None,
        search: Optional[str] = None,
        limit: int = 50
    ) -> List[GraphNode]:
        pass

    @abstractmethod
    def traverse_neighbors(self, start_node_id: str, max_depth: int = 2) -> Dict[str, Any]:
        pass

    @abstractmethod
    def decay_and_prune(self, tier: MemoryTier, ttl_seconds: float, decay_rate: float) -> int:
        pass

    @abstractmethod
    def get_graph_stats(self) -> Dict[str, Any]:
        pass


class SQLiteGraphStore(GraphStore):
    """Zero-dependency embedded graph database using SQLite."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_accessed REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    decay_score REAL NOT NULL,
                    expires_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);
                CREATE INDEX IF NOT EXISTS idx_nodes_tier ON nodes(tier);
                CREATE INDEX IF NOT EXISTS idx_nodes_decay ON nodes(decay_score);

                CREATE TABLE IF NOT EXISTS relationships (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    rel_type TEXT NOT NULL,
                    properties_json TEXT NOT NULL,
                    weight REAL NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (source_id, target_id, rel_type),
                    FOREIGN KEY (source_id) REFERENCES nodes(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES nodes(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_rel_source ON relationships(source_id);
                CREATE INDEX IF NOT EXISTS idx_rel_target ON relationships(target_id);
                CREATE INDEX IF NOT EXISTS idx_rel_type ON relationships(rel_type);
            """)

    def upsert_node(self, node: GraphNode) -> None:
        tier_str = node.tier.value if isinstance(node.tier, MemoryTier) else str(node.tier)
        props_str = json.dumps(node.properties)
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO nodes (id, label, tier, properties_json, created_at, last_accessed, access_count, decay_score, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    label = excluded.label,
                    tier = excluded.tier,
                    properties_json = excluded.properties_json,
                    last_accessed = excluded.last_accessed,
                    access_count = excluded.access_count,
                    decay_score = excluded.decay_score,
                    expires_at = excluded.expires_at
                """,
                (
                    node.id,
                    node.label,
                    tier_str,
                    props_str,
                    node.created_at,
                    node.last_accessed,
                    node.access_count,
                    node.decay_score,
                    node.expires_at,
                ),
            )

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if not row:
                return None
            node = GraphNode(
                id=row["id"],
                label=row["label"],
                tier=MemoryTier(row["tier"]),
                properties=json.loads(row["properties_json"]),
                created_at=row["created_at"],
                last_accessed=row["last_accessed"],
                access_count=row["access_count"],
                decay_score=row["decay_score"],
                expires_at=row["expires_at"],
            )
            node.touch()
            # Update touched timestamp asynchronously in next write or inline
            conn.execute(
                "UPDATE nodes SET last_accessed = ?, access_count = ?, decay_score = ? WHERE id = ?",
                (node.last_accessed, node.access_count, node.decay_score, node.id),
            )
            return node

    def delete_node(self, node_id: str) -> bool:
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            conn.execute("DELETE FROM relationships WHERE source_id = ? OR target_id = ?", (node_id, node_id))
            return cur.rowcount > 0

    def upsert_relationship(self, rel: GraphRelationship) -> None:
        props_str = json.dumps(rel.properties)
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO relationships (source_id, target_id, rel_type, properties_json, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, target_id, rel_type) DO UPDATE SET
                    properties_json = excluded.properties_json,
                    weight = excluded.weight
                """,
                (rel.source_id, rel.target_id, rel.rel_type, props_str, rel.weight, rel.created_at),
            )

    def get_relationships(self, node_id: str, direction: str = "both") -> List[GraphRelationship]:
        results = []
        with self._get_conn() as conn:
            if direction == "outgoing":
                query = "SELECT * FROM relationships WHERE source_id = ?"
                rows = conn.execute(query, (node_id,)).fetchall()
            elif direction == "incoming":
                query = "SELECT * FROM relationships WHERE target_id = ?"
                rows = conn.execute(query, (node_id,)).fetchall()
            else:
                query = "SELECT * FROM relationships WHERE source_id = ? OR target_id = ?"
                rows = conn.execute(query, (node_id, node_id)).fetchall()

            for r in rows:
                results.append(
                    GraphRelationship(
                        source_id=r["source_id"],
                        target_id=r["target_id"],
                        rel_type=r["rel_type"],
                        properties=json.loads(r["properties_json"]),
                        weight=r["weight"],
                        created_at=r["created_at"],
                    )
                )
        return results

    def query_nodes(
        self,
        label: Optional[str] = None,
        tier: Optional[MemoryTier] = None,
        search: Optional[str] = None,
        limit: int = 50
    ) -> List[GraphNode]:
        conditions = []
        params: List[Any] = []

        if label:
            conditions.append("label = ?")
            params.append(label)
        if tier:
            tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
            conditions.append("tier = ?")
            params.append(tier_str)
        if search:
            conditions.append("(id LIKE ? OR properties_json LIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM nodes {where_clause} ORDER BY decay_score DESC, last_accessed DESC LIMIT ?"
        params.append(limit)

        nodes = []
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                nodes.append(
                    GraphNode(
                        id=row["id"],
                        label=row["label"],
                        tier=MemoryTier(row["tier"]),
                        properties=json.loads(row["properties_json"]),
                        created_at=row["created_at"],
                        last_accessed=row["last_accessed"],
                        access_count=row["access_count"],
                        decay_score=row["decay_score"],
                        expires_at=row["expires_at"],
                    )
                )
        return nodes

    def traverse_neighbors(self, start_node_id: str, max_depth: int = 2) -> Dict[str, Any]:
        """Breadth-first exploration of neighboring knowledge nodes up to max_depth."""
        visited_nodes: Dict[str, Dict[str, Any]] = {}
        visited_edges: List[Dict[str, Any]] = []
        queue: List[Tuple[str, int]] = [(start_node_id, 0)]
        seen_edges: Set[Tuple[str, str, str]] = set()

        while queue:
            current_id, depth = queue.pop(0)
            if current_id not in visited_nodes:
                node = self.get_node(current_id)
                if node:
                    visited_nodes[current_id] = node.to_dict()
                else:
                    continue

            if depth >= max_depth:
                continue

            rels = self.get_relationships(current_id, direction="both")
            for r in rels:
                edge_key = (r.source_id, r.target_id, r.rel_type)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    visited_edges.append(r.to_dict())

                neighbor_id = r.target_id if r.source_id == current_id else r.source_id
                if neighbor_id not in visited_nodes:
                    queue.append((neighbor_id, depth + 1))

        return {"nodes": list(visited_nodes.values()), "edges": visited_edges}

    def decay_and_prune(self, tier: MemoryTier, ttl_seconds: float, decay_rate: float) -> int:
        """Applies decay factor to nodes and deletes expired/stale memories in the given tier."""
        tier_str = tier.value if isinstance(tier, MemoryTier) else str(tier)
        now = time.time()
        pruned_count = 0

        with self._get_conn() as conn:
            # 1. Decay scores for existing nodes in tier
            conn.execute(
                """
                UPDATE nodes
                SET decay_score = MAX(0.0, decay_score * ?)
                WHERE tier = ?
                """,
                (decay_rate, tier_str),
            )

            # 2. Prune nodes where decay_score is 0 or expires_at is passed
            # or created_at exceeds TTL for this tier
            cur = conn.execute(
                """
                DELETE FROM nodes
                WHERE tier = ? AND (
                    (expires_at IS NOT NULL AND expires_at < ?) OR
                    (? - created_at > ? AND decay_score < 0.1)
                )
                """,
                (tier_str, now, now, ttl_seconds),
            )
            pruned_count = cur.rowcount

            # Clean orphaned relationships
            conn.execute(
                """
                DELETE FROM relationships
                WHERE source_id NOT IN (SELECT id FROM nodes)
                   OR target_id NOT IN (SELECT id FROM nodes)
                """
            )

        logger.debug(f"Decayed tier {tier_str}: pruned {pruned_count} stale memory nodes.")
        return pruned_count

    def get_graph_stats(self) -> Dict[str, Any]:
        with self._get_conn() as conn:
            total_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            total_rels = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
            tier_counts = {}
            for row in conn.execute("SELECT tier, COUNT(*) as c FROM nodes GROUP BY tier").fetchall():
                tier_counts[row["tier"]] = row["c"]
            return {
                "backend": "SQLiteGraphStore",
                "database_path": str(self.db_path),
                "total_nodes": total_nodes,
                "total_relationships": total_rels,
                "tiers": tier_counts,
            }


class Neo4jGraphStore(GraphStore):
    """Neo4j graph database adapter with automatic failover to SQLiteGraphStore."""

    def __init__(self, uri: str, user: str, password: str, fallback_sqlite_path: Path):
        self.uri = uri
        self.user = user
        self.password = password
        self.fallback = SQLiteGraphStore(fallback_sqlite_path)
        self._driver = None
        self._connect()

    def _connect(self) -> None:
        try:
            import neo4j
            self._driver = neo4j.GraphDatabase.driver(self.uri, auth=(self.user, self.password))
            self._driver.verify_connectivity()
            logger.info(f"Connected to Neo4j knowledge graph database at {self.uri}")
        except Exception as e:
            logger.info(f"Neo4j connection to {self.uri} unavailable ({e}). Using embedded SQLite graph store.")
            if self._driver:
                try:
                    self._driver.close()
                except Exception:
                    pass
            self._driver = None

    def is_connected(self) -> bool:
        return self._driver is not None

    def upsert_node(self, node: GraphNode) -> None:
        # Always write to embedded fallback for resilience
        self.fallback.upsert_node(node)
        if not self._driver:
            return
        try:
            with self._driver.session() as session:
                query = f"""
                MERGE (n:{node.label} {{id: $id}})
                SET n.tier = $tier,
                    n.properties = $properties,
                    n.last_accessed = $last_accessed,
                    n.access_count = $access_count,
                    n.decay_score = $decay_score
                """
                session.run(
                    query,
                    id=node.id,
                    tier=node.tier.value if isinstance(node.tier, MemoryTier) else str(node.tier),
                    properties=json.dumps(node.properties),
                    last_accessed=node.last_accessed,
                    access_count=node.access_count,
                    decay_score=node.decay_score,
                )
        except Exception as e:
            logger.warning(f"Failed to sync node {node.id} to Neo4j: {e}")

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        # Fast local read with full support
        return self.fallback.get_node(node_id)

    def delete_node(self, node_id: str) -> bool:
        res = self.fallback.delete_node(node_id)
        if self._driver:
            try:
                with self._driver.session() as session:
                    session.run("MATCH (n {id: $id}) DETACH DELETE n", id=node_id)
            except Exception as e:
                logger.warning(f"Failed to delete node {node_id} in Neo4j: {e}")
        return res

    def upsert_relationship(self, rel: GraphRelationship) -> None:
        self.fallback.upsert_relationship(rel)
        if not self._driver:
            return
        try:
            with self._driver.session() as session:
                query = f"""
                MATCH (s {{id: $source_id}}), (t {{id: $target_id}})
                MERGE (s)-[r:{rel.rel_type}]->(t)
                SET r.weight = $weight, r.properties = $properties
                """
                session.run(
                    query,
                    source_id=rel.source_id,
                    target_id=rel.target_id,
                    weight=rel.weight,
                    properties=json.dumps(rel.properties),
                )
        except Exception as e:
            logger.warning(f"Failed to sync relationship {rel.rel_type} to Neo4j: {e}")

    def get_relationships(self, node_id: str, direction: str = "both") -> List[GraphRelationship]:
        return self.fallback.get_relationships(node_id, direction=direction)

    def query_nodes(
        self,
        label: Optional[str] = None,
        tier: Optional[MemoryTier] = None,
        search: Optional[str] = None,
        limit: int = 50
    ) -> List[GraphNode]:
        return self.fallback.query_nodes(label=label, tier=tier, search=search, limit=limit)

    def traverse_neighbors(self, start_node_id: str, max_depth: int = 2) -> Dict[str, Any]:
        return self.fallback.traverse_neighbors(start_node_id=start_node_id, max_depth=max_depth)

    def decay_and_prune(self, tier: MemoryTier, ttl_seconds: float, decay_rate: float) -> int:
        return self.fallback.decay_and_prune(tier=tier, ttl_seconds=ttl_seconds, decay_rate=decay_rate)

    def get_graph_stats(self) -> Dict[str, Any]:
        stats = self.fallback.get_graph_stats()
        stats["backend"] = "Neo4jGraphStore" if self._driver else "Neo4jGraphStore (Offline - SQLite Active)"
        stats["neo4j_connected"] = self.is_connected()
        stats["neo4j_uri"] = self.uri
        return stats


def create_graph_store(
    db_path: Path,
    neo4j_uri: Optional[str] = None,
    neo4j_user: Optional[str] = None,
    neo4j_password: Optional[str] = None
) -> GraphStore:
    """Factory creating a unified GraphStore with Neo4j support and SQLite persistence."""
    if neo4j_uri and neo4j_user and neo4j_password:
        return Neo4jGraphStore(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
            fallback_sqlite_path=db_path
        )
    return SQLiteGraphStore(db_path=db_path)
