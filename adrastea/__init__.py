"""
Adrastea: Dual-System Autonomous Orchestrator.
Alpha (Deterministic Execution Engine) & Beta (Probabilistic Cognitive Engine).
"""

import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

__version__ = "0.1.0"

from .keepalive import KeepAliveProcess

__all__ = ["KeepAliveProcess", "__version__"]
