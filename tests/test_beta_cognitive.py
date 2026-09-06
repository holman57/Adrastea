import asyncio
import unittest
from adrastea.beta.llm_consultant import LLMConsultant
from adrastea.beta.mcp_client import MCPClient
from adrastea.beta.triage import TriageEngine
from adrastea.beta.tuner import HeuristicTuner
from adrastea.beta.discovery import GoalDiscovery
from adrastea.ipc.protocol import SignalType


class DummyLLMConsultant(LLMConsultant):
    def consult(self, prompt: str, system_prompt=None, max_tokens=1024) -> str:
        return '{"action": "MUTATE", "new_command": "echo repaired"}'


class TestBetaCognitive(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.llm = DummyLLMConsultant()
        self.triage = TriageEngine(llm=self.llm)
        self.tuner = HeuristicTuner()
        self.discovery = GoalDiscovery(llm=self.llm)
        self.mcp = MCPClient()

    def test_triage_stuck_state(self):
        stuck_payload = {
            "task_id": "stuck_task_1",
            "command": "infinite_loop.exe",
            "consecutive_failures": 5,
            "last_error": "TimeoutExpired"
        }
        signals = self.triage.analyze_stuck_state(stuck_payload)
        signal_types = [s.signal for s in signals]

        self.assertIn(SignalType.SIG_INTERRUPT, signal_types)
        self.assertIn(SignalType.SIG_TUNE_WEIGHTS, signal_types)
        self.assertIn(SignalType.SIG_MUTATE, signal_types)

    def test_heuristic_tuner_elevated_failure(self):
        telemetry = {
            "total_executions": 10,
            "total_failures": 4,
            "weights": {"w_error_penalty": 15.0, "exploration_rate": 0.15}
        }
        msg = self.tuner.evaluate_telemetry(telemetry)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.signal, SignalType.SIG_TUNE_WEIGHTS)
        self.assertGreater(msg.payload["weights"]["w_error_penalty"], 15.0)

    async def test_mcp_client_tools(self):
        tools = await self.mcp.list_tools()
        tool_names = [t["name"] for t in tools]
        self.assertIn("inspect_system_health", tool_names)

        result = await self.mcp.call_tool("inspect_system_health", {})
        self.assertIn("cpu_percent", result)
        self.assertIn("memory_percent", result)


if __name__ == "__main__":
    unittest.main()
