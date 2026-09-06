import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Adrastea.Beta.MCP")


class MCPClient:
    """Model Context Protocol (MCP) client for System Beta."""

    def __init__(self, server_command: Optional[List[str]] = None):
        self.server_command = server_command
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: Dict[str, Dict[str, Any]] = {}
        self.request_id = 0

        # Register standard built-in MCP tools for Adrastea
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Built-in default tools available to Beta."""
        self.tools["inspect_system_health"] = {
            "name": "inspect_system_health",
            "description": "Check CPU, memory, and active processes",
            "parameters": {"type": "object", "properties": {}}
        }
        self.tools["generate_diagnostic_script"] = {
            "name": "generate_diagnostic_script",
            "description": "Create a temporary local python script to test a subsystem",
            "parameters": {
                "type": "object",
                "properties": {
                    "script_name": {"type": "string"},
                    "code": {"type": "string"}
                },
                "required": ["script_name", "code"]
            }
        }
        self.tools["query_execution_history"] = {
            "name": "query_execution_history",
            "description": "Query historical success/failure rates of Alpha's tasks",
            "parameters": {"type": "object", "properties": {}}
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools in MCP catalog."""
        return list(self.tools.values())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool call."""
        logger.info(f"Executing MCP tool call [{name}] with args: {arguments}")
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}

        # Execution of built-ins
        if name == "inspect_system_health":
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage_percent": psutil.disk_usage("C:\\").percent
            }
        elif name == "generate_diagnostic_script":
            from ..config import config
            script_path = config.data_dir / arguments["script_name"]
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(arguments["code"])
            return {"status": "created", "path": str(script_path)}
        elif name == "query_execution_history":
            return {"status": "success", "tools_count": len(self.tools)}

        return {"status": "executed", "result": None}
