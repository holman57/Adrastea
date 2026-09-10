import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from adrastea.alpha.solved_problems import (
    apply_code_patch,
    inspect_repository,
    post_progress_and_pause,
    loop_target_repositories_step,
    run_tests,
)
from adrastea.knowledge.prompt_compiler import CognitivePromptCompiler
from adrastea.beta.mcp_client import MCPClient


class TestSolvedProblemsAndPromptCompiler(unittest.TestCase):

    def test_inspect_repository_and_configs(self):
        # Inspect hardcode repository
        res = inspect_repository("hardcode")
        self.assertTrue(res.get("exists"))
        self.assertIn(".adrastea.json", res.get("configs", []))
        self.assertIsNotNone(res.get("adrastea_config"))
        self.assertEqual(res.get("adrastea_config", {}).get("name"), "hardcode")

    def test_apply_code_patch_and_syntax_validation(self):
        with patch("pathlib.Path.mkdir"), patch("builtins.open", unittest.mock.mock_open()) as mock_file:
            with patch("adrastea.alpha.solved_problems.get_repo_path") as mock_repo_path:
                mock_dir = MagicMock()
                mock_dir.is_dir.return_value = True
                mock_dir.__truediv__.return_value = Path("C:/mock/test.json")
                mock_repo_path.return_value = mock_dir

                # Valid JSON
                valid_res = apply_code_patch("mock_repo", {"test.json": '{"valid": true}'})
                self.assertTrue(valid_res["success"])
                self.assertIn("test.json", valid_res["written_files"])

                # Invalid JSON syntax should fail validation
                invalid_res = apply_code_patch("mock_repo", {"broken.json": '{"invalid": true,'})
                self.assertFalse(invalid_res["success"])
                self.assertEqual(len(invalid_res["errors"]), 1)

    def test_prompt_compiler_compiles_all_tiers(self):
        compiler = CognitivePromptCompiler()
        compiled = compiler.compile_task_prompt(
            repo_name="hardcode",
            issue_data={
                "number": 2,
                "title": "New Question Types & db.json Schema Expansion",
                "body": "Add support for True/False, Matching, Sequencing, Sorting question models",
                "author": "holman57",
            },
            repo_config={"name": "hardcode", "version": "1.1.0"},
            task_context={"test_output": "All 8 tests passing"},
        )
        self.assertIn("system_prompt", compiled)
        self.assertIn("user_prompt", compiled)
        self.assertIn("metadata", compiled)

        meta = compiled["metadata"]
        self.assertEqual(meta["repo"], "hardcode")
        self.assertEqual(meta["issue_number"], 2)
        self.assertGreater(meta["estimated_tokens"], 100)
        self.assertEqual(meta["memory_tiers_used"], ["SHORT_TERM", "MEDIUM_TERM", "LONG_TERM"])

        user_p = compiled["user_prompt"]
        self.assertIn("=== TARGET REPOSITORY CONTEXT ===", user_p)
        self.assertIn("=== KNOWLEDGE GRAPH MEMORY CONTEXT ===", user_p)
        self.assertIn("=== ACTIONABLE TASK ===", user_p)

    def test_mcp_client_tools_list_and_offload(self):
        client = MCPClient()
        tools = asyncio.run(client.list_tools())
        names = [t["name"] for t in tools]

        self.assertIn("run_local_llm", names)
        self.assertIn("query_knowledge_graph", names)
        self.assertIn("compile_cognitive_prompt", names)
        self.assertIn("offload_solved_problem", names)

    @patch("subprocess.run")
    def test_post_progress_and_pause_mocked(self, mock_subproc):
        m = MagicMock()
        m.returncode = 0
        m.stdout = "https://github.com/holman57/hardcode/issues/2#issuecomment-9999\n"
        m.stderr = ""
        mock_subproc.return_value = m

        res = post_progress_and_pause(
            repo_name="hardcode",
            issue_number=2,
            progress_summary="Implemented question models.",
            pr_url="https://github.com/holman57/hardcode/pull/7",
            guidance_request="Review PR #7.",
        )
        self.assertTrue(res["success"])
        self.assertTrue(res["paused"])
        self.assertEqual(res["issue_number"], 2)


if __name__ == "__main__":
    unittest.main()
