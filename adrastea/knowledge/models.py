import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MemoryTier(str, Enum):
    """Multi-tiered memory lifecycle partitions for Adrastea."""
    SHORT_TERM = "SHORT_TERM"    # Working memory / episodic buffer (task traces, immediate telemetry, logs)
    MEDIUM_TERM = "MEDIUM_TERM"  # Tactical memory (failure patterns, weekly heuristics, directive history)
    LONG_TERM = "LONG_TERM"      # Semantic knowledge (core ontology, companion repo architecture, user identity)


@dataclass
class GraphNode:
    """Represents an entity, concept, or memory node in the knowledge graph."""
    id: str
    label: str
    tier: MemoryTier = MemoryTier.SHORT_TERM
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 1
    decay_score: float = 1.0  # 1.0 = fully fresh, decaying towards 0.0
    expires_at: Optional[float] = None

    def touch(self) -> None:
        """Mark node as recently accessed, boosting its decay resilience."""
        self.last_accessed = time.time()
        self.access_count += 1
        self.decay_score = min(1.0, self.decay_score + 0.15)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "tier": self.tier.value if isinstance(self.tier, MemoryTier) else str(self.tier),
            "properties": self.properties,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "decay_score": round(self.decay_score, 3),
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphNode":
        tier_val = data.get("tier", MemoryTier.SHORT_TERM.value)
        tier = MemoryTier(tier_val) if isinstance(tier_val, str) else tier_val
        return cls(
            id=data["id"],
            label=data["label"],
            tier=tier,
            properties=data.get("properties", {}),
            created_at=data.get("created_at", time.time()),
            last_accessed=data.get("last_accessed", time.time()),
            access_count=data.get("access_count", 1),
            decay_score=data.get("decay_score", 1.0),
            expires_at=data.get("expires_at"),
        )


@dataclass
class GraphRelationship:
    """Directed, weighted relationship connecting two memory nodes."""
    source_id: str
    target_id: str
    rel_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "rel_type": self.rel_type,
            "properties": self.properties,
            "weight": self.weight,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphRelationship":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            rel_type=data["rel_type"],
            properties=data.get("properties", {}),
            weight=data.get("weight", 1.0),
            created_at=data.get("created_at", time.time()),
        )
