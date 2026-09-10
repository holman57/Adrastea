import asyncio
import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from ..config import config

logger = logging.getLogger("Adrastea.Beta.MCP")


class MCPClient:
    """Model Context Protocol (MCP) client for System Beta.
    Exposes local LLM execution, knowledge graph queries, prompt compilation,
    and Alpha's Solved Problems offloading.
    """

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
        self.tools["run_local_llm"] = {
            "name": "run_local_llm",
            "description": "Execute local LLM inference via Ollama or local endpoint over MCP",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "system": {"type": "string"},
                    "model": {"type": "string"},
                    "temperature": {"type": "number"}
                },
                "required": ["prompt"]
            }
        }
        self.tools["query_knowledge_graph"] = {
            "name": "query_knowledge_graph",
            "description": "Query nodes, relationships, and context from multi-tier graph memory",
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["search"]
            }
        }
        self.tools["compile_cognitive_prompt"] = {
            "name": "compile_cognitive_prompt",
            "description": "Compile, summarize, and optimize cognitive prompts from graph memory and repo configs",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string"},
                    "issue_data": {"type": "object"},
                    "repo_config": {"type": "object"},
                    "task_context": {"type": "object"}
                },
                "required": ["repo_name", "issue_data"]
            }
        }
        self.tools["offload_solved_problem"] = {
            "name": "offload_solved_problem",
            "description": "Offload procedural tasks (patching, testing, git branches, PRs, comments) to Alpha as Solved Problems",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "parameters": {"type": "object"}
                },
                "required": ["action", "parameters"]
            }
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List all available tools in MCP catalog."""
        return list(self.tools.values())

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an MCP tool call."""
        logger.info(f"Executing MCP tool call [{name}] with args: {list(arguments.keys())}")
        if name not in self.tools:
            return {"error": f"Tool '{name}' not found."}

        # 1. System health
        if name == "inspect_system_health":
            import psutil
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage_percent": psutil.disk_usage("C:\\").percent
            }

        # 2. Diagnostic script
        elif name == "generate_diagnostic_script":
            script_path = config.data_dir / arguments["script_name"]
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(arguments["code"])
            return {"status": "created", "path": str(script_path)}

        # 3. Execution history
        elif name == "query_execution_history":
            return {"status": "success", "tools_count": len(self.tools)}

        # 4. Local LLM via MCP
        elif name == "run_local_llm":
            prompt = arguments.get("prompt", "")
            system = arguments.get("system")
            model = arguments.get("model") or config.ollama_model
            temp = float(arguments.get("temperature", 0.3))
            
            url = f"{config.ollama_base_url}/api/generate"
            payload: Dict[str, Any] = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temp}
            }
            if system:
                payload["system"] = system

            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
                loop = asyncio.get_event_loop()
                # Run synchronous urlopen in executor
                def do_request():
                    with urllib.request.urlopen(req, timeout=45) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                
                result = await loop.run_in_executor(None, do_request)
                return {
                    "status": "success",
                    "provider": "local_ollama_mcp",
                    "model": model,
                    "response": result.get("response", "").strip()
                }
            except Exception as e:
                logger.warning(f"Local LLM via MCP failed: {e}")
                return {
                    "status": "fallback",
                    "provider": "local_ollama_mcp",
                    "error": str(e),
                    "response": f"[Local LLM via MCP Offline Fallback: {e}]"
                }

        # 5. Query Knowledge Graph
        elif name == "query_knowledge_graph":
            search_query = arguments.get("search", "")
            limit = int(arguments.get("limit", 5))
            from ..knowledge.memory_manager import MemoryManager
            mm = MemoryManager()
            recalled = mm.recall_context(search_term=search_query, limit=limit)
            return {"status": "success", "results": recalled}

        # 6. Compile Cognitive Prompt
        elif name == "compile_cognitive_prompt":
            repo_name = arguments.get("repo_name", "")
            issue_data = arguments.get("issue_data", {})
            repo_config = arguments.get("repo_config")
            task_context = arguments.get("task_context")
            from ..knowledge.prompt_compiler import CognitivePromptCompiler
            compiler = CognitivePromptCompiler()
            compiled = compiler.compile_task_prompt(
                repo_name=repo_name,
                issue_data=issue_data,
                repo_config=repo_config,
                task_context=task_context,
            )
            return {"status": "success", "compiled_prompt": compiled}

        # 7. Offload Solved Problem to Alpha
        elif name == "offload_solved_problem":
            action = arguments.get("action", "")
            params = arguments.get("parameters", {})
            from ..alpha import solved_problems as sp
            if not hasattr(sp, action):
                return {"error": f"Solved problem action '{action}' not recognized in Alpha."}
            
            func = getattr(sp, action)
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(None, lambda: func(**params))
                return {"status": "success", "action": action, "result": result}
            except Exception as e:
                logger.error(f"Error executing solved problem {action}: {e}")
                return {"status": "error", "action": action, "error": str(e)}

        return {"status": "executed", "result": None}
