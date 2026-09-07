import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class SignalType(str, Enum):
    # Lifecycle & Heartbeats
    SIG_SPAWN = "SIG_SPAWN"
    SIG_HEARTBEAT = "SIG_HEARTBEAT"
    SIG_SHUTDOWN = "SIG_SHUTDOWN"
    SIG_SLEEP = "SIG_SLEEP"
    SIG_WAKE = "SIG_WAKE"

    # Alpha -> Beta
    SIG_TELEMETRY = "SIG_TELEMETRY"
    SIG_STUCK = "SIG_STUCK"
    SIG_TASK_COMPLETED = "SIG_TASK_COMPLETED"
    SIG_TASK_FAILED = "SIG_TASK_FAILED"

    # Beta -> Alpha
    SIG_INTERRUPT = "SIG_INTERRUPT"
    SIG_DISPATCH = "SIG_DISPATCH"
    SIG_MUTATE = "SIG_MUTATE"
    SIG_TUNE_WEIGHTS = "SIG_TUNE_WEIGHTS"
    SIG_TUNE_GOALS = "SIG_TUNE_GOALS"
    SIG_QUERY_GOALS = "SIG_QUERY_GOALS"
    SIG_QUERY_STATUS = "SIG_QUERY_STATUS"

    # Bidirectional Goals / Memory Telemetry
    SIG_GOALS_STATUS = "SIG_GOALS_STATUS"

    # Speech Flow & Conversational Interface
    SIG_CONVERSATION = "SIG_CONVERSATION"


@dataclass
class Message:
    signal: SignalType
    sender: str  # "Alpha" or "Beta"
    payload: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal.value if isinstance(self.signal, SignalType) else str(self.signal),
            "sender": self.sender,
            "payload": self.payload,
            "message_id": self.message_id,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict()) + "\n"

    @classmethod
    def from_json(cls, line: str) -> "Message":
        data = json.loads(line.strip())
        return cls(
            signal=SignalType(data["signal"]),
            sender=data["sender"],
            payload=data.get("payload", {}),
            message_id=data.get("message_id", str(uuid.uuid4())[:8]),
            timestamp=data.get("timestamp", time.time()),
        )
