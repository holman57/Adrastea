import tempfile
import time
import unittest
from pathlib import Path

from adrastea.knowledge.graph_store import SQLiteGraphStore
from adrastea.knowledge.memory_manager import MemoryManager
from adrastea.knowledge.models import GraphNode, GraphRelationship, MemoryTier


class TestKnowledgeGraph(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_knowledge.db"
        self.store = SQLiteGraphStore(self.db_path)
        self.memory = MemoryManager(store=self.store)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_node_and_relationship_crud(self):
        # Create node
        node = GraphNode(
            id="node_concept_1",
            label="Concept",
            tier=MemoryTier.LONG_TERM,
            properties={"topic": "Reinforcement Learning", "scope": "Alpha Planner"},
        )
        self.store.upsert_node(node)

        fetched = self.store.get_node("node_concept_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.label, "Concept")
        self.assertEqual(fetched.tier, MemoryTier.LONG_TERM)
        self.assertEqual(fetched.properties["topic"], "Reinforcement Learning")

        # Create second node
        node2 = GraphNode(
            id="node_task_1",
            label="Task",
            tier=MemoryTier.SHORT_TERM,
            properties={"command": "python test.py"},
        )
        self.store.upsert_node(node2)

        # Connect them
        rel = GraphRelationship(
            source_id="node_concept_1",
            target_id="node_task_1",
            rel_type="APPLIES_TO",
            weight=1.5,
        )
        self.store.upsert_relationship(rel)

        rels = self.store.get_relationships("node_concept_1", direction="outgoing")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].rel_type, "APPLIES_TO")
        self.assertEqual(rels[0].target_id, "node_task_1")

    def test_graph_traversal(self):
        # Node A -> Node B -> Node C
        nA = GraphNode(id="A", label="Entity", properties={"name": "Alpha"})
        nB = GraphNode(id="B", label="Entity", properties={"name": "Beta"})
        nC = GraphNode(id="C", label="Entity", properties={"name": "Gamma"})
        for n in [nA, nB, nC]:
            self.store.upsert_node(n)

        self.store.upsert_relationship(GraphRelationship("A", "B", "CONNECTS"))
        self.store.upsert_relationship(GraphRelationship("B", "C", "CONNECTS"))

        traversal = self.store.traverse_neighbors("A", max_depth=2)
        node_ids = {n["id"] for n in traversal["nodes"]}
        self.assertIn("A", node_ids)
        self.assertIn("B", node_ids)
        self.assertIn("C", node_ids)

    def test_memory_tier_decay_and_prune(self):
        now = time.time()
        # Create an expired short term node
        expired_node = GraphNode(
            id="expired_stm",
            label="Log",
            tier=MemoryTier.SHORT_TERM,
            created_at=now - 1000,
            expires_at=now - 50,
            decay_score=0.05,
        )
        self.store.upsert_node(expired_node)

        pruned = self.store.decay_and_prune(MemoryTier.SHORT_TERM, ttl_seconds=500.0, decay_rate=0.5)
        self.assertGreaterEqual(pruned, 1)
        self.assertIsNone(self.store.get_node("expired_stm"))

    def test_memory_manager_domain_operations(self):
        # 1. Root ontology seeded
        self.assertIsNotNone(self.store.get_node("adrastea_system"))
        self.assertIsNotNone(self.store.get_node("user_luke"))

        # 2. Record task execution
        trace_id = self.memory.record_task_execution(
            task_id="test_diag",
            command="python -c 'print(1)'",
            result={"exit_code": 0, "duration": 0.1, "stdout_sample": "1", "stderr_sample": ""}
        )
        self.assertTrue(trace_id.startswith("stm_tasktrace_"))

        # 3. Record task failure creates FailurePattern in medium term
        fail_trace_id = self.memory.record_task_execution(
            task_id="failing_task",
            command="python -c 'exit(1)'",
            result={"exit_code": 1, "duration": 0.1, "stdout_sample": "", "stderr_sample": "AssertionError"}
        )
        pattern = self.store.get_node("pattern_fail_failing_task")
        self.assertIsNotNone(pattern)
        self.assertEqual(pattern.tier, MemoryTier.MEDIUM_TERM)

        # 4. Record user directive
        d_id = self.memory.record_user_directive("Improve speech-flow interface", source="DIRECTIVES.txt")
        self.assertIsNotNone(self.store.get_node(d_id))
        self.assertEqual(self.store.get_node(d_id).tier, MemoryTier.LONG_TERM)

        # 5. Record companion project
        proj_id = self.memory.record_companion_project("speech-flow", {"status": "in-progress"})
        self.assertEqual(proj_id, "project_speech_flow")
        self.assertIsNotNone(self.store.get_node(proj_id))

        # 6. Context recall
        recalled = self.memory.recall_context("speech-flow")
        self.assertTrue(len(recalled) > 0)


if __name__ == "__main__":
    unittest.main()
