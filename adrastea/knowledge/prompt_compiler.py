import json
import logging
import time
from typing import Any, Dict, List, Optional

from ..config import config
from .memory_manager import MemoryManager
from .models import MemoryTier

logger = logging.getLogger("Adrastea.Knowledge.PromptCompiler")

AUTHORIZED_OPERATOR = "holman57"


class CognitivePromptCompiler:
    """Compiles, summarizes, and optimizes cognitive task prompts for System Beta
    by referencing the multi-tiered graph knowledge base (Short, Medium, and Long-Term Memory).
    
    Composes graph memories with outputs from tasks, GitHub issue inputs, and repository
    configuration files (.adrastea.json).
    """

    def __init__(self, memory_manager: Optional[MemoryManager] = None):
        self.memory = memory_manager or MemoryManager()

    def _gather_long_term_context(self, repo_name: str) -> Dict[str, Any]:
        """Extract permanent semantic knowledge: User identity, system capabilities,
        and repo architectural nodes from long-term memory.
        """
        ltm_data: Dict[str, Any] = {
            "operator": "holman57 (Luke Holman) - Sole Decision Authority",
            "solved_problems": [
                "inspect_repository",
                "apply_code_patch",
                "run_tests",
                "create_feature_branch_and_commit",
                "push_and_open_pull_request",
                "post_progress_and_pause",
                "loop_target_repositories_step",
            ],
            "directives": [],
            "project_profile": None,
        }

        # Query repo project node
        clean_name = repo_name.lower().replace("-", "_")
        proj_node = self.memory.store.get_node(f"project_{clean_name}")
        if proj_node:
            ltm_data["project_profile"] = proj_node.properties

        # Query adopted user directives
        directive_nodes = self.memory.store.query_nodes(label="UserDirective", tier=MemoryTier.LONG_TERM, limit=5)
        for d in directive_nodes:
            directive_text = d.properties.get("directive", "")
            if directive_text:
                ltm_data["directives"].append(directive_text[:150])

        return ltm_data

    def _gather_medium_term_context(self, repo_name: str) -> Dict[str, Any]:
        """Extract tactical heuristics: recurring failure patterns, past bug resolutions,
        and optimization rules from medium-term memory.
        """
        mtm_data: Dict[str, Any] = {
            "failure_patterns": [],
            "tactical_guidelines": [
                "Encapsulate deterministic behavior into Alpha Solved Problems.",
                "Offload procedural tasks (git, tests, file writes, comments) onto Alpha.",
                "Always run automated tests before submitting a Pull Request.",
                "Post a progress update to the issue and pause for operator guidance upon completing tasks in a repo.",
                "Respect anti-spam backoff: do not repeatedly ping operator without new work or elapsed wait period.",
            ],
        }

        # Query failure patterns
        fail_nodes = self.memory.store.query_nodes(label="FailurePattern", tier=MemoryTier.MEDIUM_TERM, limit=5)
        for fn in fail_nodes:
            err = fn.properties.get("last_error", "")
            task_id = fn.properties.get("task_id", "")
            if err:
                mtm_data["failure_patterns"].append(f"Task {task_id}: {err[:120]}")

        return mtm_data

    def _gather_short_term_context(self, repo_name: str, task_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract transient episodic memory: recent task execution traces, test outputs,
        and latest conversation telemetry from short-term memory.
        """
        stm_data: Dict[str, Any] = {
            "recent_traces": [],
            "latest_test_output": None,
        }

        # Query recent task traces
        traces = self.memory.store.query_nodes(label="TaskTrace", tier=MemoryTier.SHORT_TERM, limit=3)
        for t in traces:
            stm_data["recent_traces"].append({
                "task_id": t.properties.get("task_id"),
                "success": t.properties.get("success"),
                "exit_code": t.properties.get("exit_code"),
                "duration": t.properties.get("duration"),
            })

        if task_context:
            if "test_output" in task_context:
                stm_data["latest_test_output"] = str(task_context["test_output"])[:300]

        return stm_data

    def compile_task_prompt(
        self,
        repo_name: str,
        issue_data: Dict[str, Any],
        repo_config: Optional[Dict[str, Any]] = None,
        task_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Synthesizes, summarizes, and optimizes a cognitive prompt across:
        1. Long-Term Memory (Identity, Solved Problems, Architectural specs)
        2. Medium-Term Memory (Tactical heuristics, Failure patterns)
        3. Short-Term Memory (Recent task traces, immediate telemetry)
        4. Repo Configuration (.adrastea.json)
        5. Issue Requirements & Operator Guidance
        """
        ltm = self._gather_long_term_context(repo_name)
        mtm = self._gather_medium_term_context(repo_name)
        stm = self._gather_short_term_context(repo_name, task_context)

        issue_num = issue_data.get("number", "N/A")
        issue_title = issue_data.get("title", "")
        issue_body = issue_data.get("body", "")
        issue_author = issue_data.get("author", AUTHORIZED_OPERATOR)

        # 1. High-Density System Prompt
        system_prompt = (
            "You are System Beta, the cognitive strategist and paired reasoning engine for Adrastea. "
            "You pair with System Alpha, which deterministically executes 'Solved Problems' (code patching, "
            "running tests, git commits/PRs, progress updates, and anti-spam pausing). "
            "Your objective is to analyze requirements, plan concise solutions, formulate code modifications, "
            "and offload procedural execution to Alpha. "
            "Always follow operator directives from Luke Holman (@holman57) as the ultimate specification."
        )

        # 2. Optimized Structured User Prompt
        directives_block = "\n".join(f"- {d}" for d in ltm["directives"][:3]) if ltm["directives"] else "- None recorded yet."
        guidelines_block = "\n".join(f"- {g}" for g in mtm["tactical_guidelines"][:4])
        failures_block = "\n".join(f"- {f}" for f in mtm["failure_patterns"][:2]) if mtm["failure_patterns"] else "- No active failure patterns."
        traces_block = "\n".join(f"- {t['task_id']} (Success={t['success']}, Code={t['exit_code']})" for t in stm["recent_traces"]) if stm["recent_traces"] else "- Clean history."

        config_summary = json.dumps(repo_config or {}, indent=2) if repo_config else "{}"

        user_prompt = (
            f"=== TARGET REPOSITORY CONTEXT ===\n"
            f"Repository: {repo_name}\n"
            f"Issue #{issue_num}: {issue_title}\n"
            f"Author: @{issue_author}\n\n"
            f"=== ISSUE REQUIREMENT / OPERATOR DIRECTIVE ===\n"
            f"{issue_body.strip()}\n\n"
            f"=== REPOSITORY CONFIGURATION (.adrastea.json) ===\n"
            f"{config_summary}\n\n"
            f"=== KNOWLEDGE GRAPH MEMORY CONTEXT ===\n"
            f"[Long-Term Memory: Core Directives]\n"
            f"{directives_block}\n\n"
            f"[Medium-Term Memory: Tactical Rules & Heuristics]\n"
            f"{guidelines_block}\n"
            f"[Medium-Term Memory: Failure Patterns to Avoid]\n"
            f"{failures_block}\n\n"
            f"[Short-Term Memory: Recent Traces & Telemetry]\n"
            f"{traces_block}\n\n"
            f"=== ACTIONABLE TASK ===\n"
            f"Synthesize the solution for Issue #{issue_num} in `{repo_name}`. "
            f"Determine the exact files to modify or create, the deterministic validation test, "
            f"and the progress summary to report back to Luke Holman (@holman57). "
            f"Offload procedural tasks (patching, testing, committing, PR, and posting progress) "
            f"to Alpha's Solved Problems."
        )

        # Estimate token count (~4 chars per token)
        est_tokens = len(system_prompt) // 4 + len(user_prompt) // 4

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "metadata": {
                "repo": repo_name,
                "issue_number": issue_num,
                "estimated_tokens": est_tokens,
                "timestamp": time.time(),
                "memory_tiers_used": ["SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"],
            }
        }
