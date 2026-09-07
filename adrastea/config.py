import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def load_dotenv(dotenv_path: Optional[Path] = None) -> None:
    """Lightweight built-in .env parser to avoid external dependencies."""
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    
    if not dotenv_path.is_file():
        return

    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass


# Ensure .env is loaded on import
load_dotenv()


@dataclass
class Config:
    """Central configuration for Adrastea (Alpha & Beta)."""
    # Environment & Paths
    env: str = os.getenv("ADRASTEA_ENV", "development")
    root_dir: Path = Path(__file__).resolve().parent.parent
    data_dir: Path = root_dir / "data"
    logs_dir: Path = root_dir / "logs"

    # IPC Settings
    ipc_host: str = os.getenv("ADRASTEA_IPC_HOST", "127.0.0.1")
    ipc_port: int = int(os.getenv("ADRASTEA_IPC_PORT", "8765"))
    ipc_auth_token: str = os.getenv("ADRASTEA_IPC_TOKEN", "adrastea-local-secure-token")

    # Keep-Alive & Standby Settings
    keepalive_sleep_seconds: float = float(os.getenv("ADRASTEA_KEEPALIVE_SLEEP_SECONDS", "300.0"))
    keepalive_heartbeat_interval: float = float(os.getenv("ADRASTEA_HEARTBEAT_INTERVAL", "60.0"))

    # Alpha Engine Settings
    alpha_tick_interval: float = float(os.getenv("ALPHA_TICK_INTERVAL_SECONDS", "3.0"))
    alpha_stabilization_seconds: float = float(os.getenv("ALPHA_STABILIZATION_SECONDS", "2.0"))
    alpha_max_concurrent_tasks: int = int(os.getenv("ALPHA_MAX_CONCURRENT_TASKS", "4"))

    # Beta Engine Settings
    beta_tick_interval: float = float(os.getenv("BETA_TICK_INTERVAL_SECONDS", "5.0"))
    beta_idle_cycle_seconds: float = float(os.getenv("BETA_IDLE_CYCLE_SECONDS", "30.0"))
    beta_enable_mcp: bool = os.getenv("BETA_ENABLE_MCP", "true").lower() == "true"

    # Local LLM (Ollama)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3-coder:30b")

    # Frontier / Cloud LLM (Gemini)
    gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY", None)
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # Notification Recipients (Configured via .env or environment variables; never hardcoded)
    target_email: Optional[str] = field(default_factory=lambda: os.getenv("NOTIFICATION_TARGET_EMAIL", None))
    target_phone: Optional[str] = field(default_factory=lambda: os.getenv("NOTIFICATION_TARGET_PHONE", None))
    notification_interval_minutes: int = int(os.getenv("NOTIFICATION_INTERVAL_MINUTES", "60"))

    # Email Dispatcher
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: Optional[str] = os.getenv("SMTP_USER", None)
    smtp_password: Optional[str] = os.getenv("SMTP_PASSWORD", None)
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    # SMS Dispatcher
    sms_carrier_gateway: str = os.getenv("SMS_CARRIER_GATEWAY", "att")  # att, verizon, tmobile, sprint
    twilio_account_sid: Optional[str] = os.getenv("TWILIO_ACCOUNT_SID", None)
    twilio_auth_token: Optional[str] = os.getenv("TWILIO_AUTH_TOKEN", None)
    twilio_from_number: Optional[str] = os.getenv("TWILIO_FROM_NUMBER", None)

    # Voice Notifications (Disabled by default; only active when speech-flow is running)
    enable_voice_notifications: bool = os.getenv("ADRASTEA_ENABLE_VOICE", "false").lower() == "true"
    speech_flow_port: int = int(os.getenv("SPEECH_FLOW_PORT", "7860"))

    # Knowledge Base & Graph Database (Neo4j with embedded SQLite fallback)
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "password")
    knowledge_db_path: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent / "data" / "knowledge_graph.db")

    # Companion AI Managed Repositories
    companion_workspace_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent.parent.parent)

    def __post_init__(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_db_path.parent.mkdir(parents=True, exist_ok=True)


config = Config()
