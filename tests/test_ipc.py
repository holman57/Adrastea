import asyncio
import unittest
from adrastea.ipc.protocol import Message, SignalType
from adrastea.ipc.channel import IPCServer, IPCClient


class TestIPC(unittest.IsolatedAsyncioTestCase):
    def test_message_serialization(self):
        msg = Message(
            signal=SignalType.SIG_INTERRUPT,
            sender="Beta",
            payload={"task_id": "test_123"}
        )
        json_str = msg.to_json()
        self.assertIn("SIG_INTERRUPT", json_str)
        self.assertIn("test_123", json_str)

        restored = Message.from_json(json_str)
        self.assertEqual(restored.signal, SignalType.SIG_INTERRUPT)
        self.assertEqual(restored.sender, "Beta")
        self.assertEqual(restored.payload.get("task_id"), "test_123")

    async def test_server_client_communication(self):
        # Use a dynamic high port for testing
        test_port = 8990
        server = IPCServer(host="127.0.0.1", port=test_port)
        received_by_server = []

        async def handle_telemetry(msg: Message):
            received_by_server.append(msg)
            return Message(signal=SignalType.SIG_HEARTBEAT, sender="Alpha", payload={"ack": True})

        server.register_handler(SignalType.SIG_TELEMETRY, handle_telemetry)
        await server.start()

        client = IPCClient(host="127.0.0.1", port=test_port)
        connected = await client.connect(retries=3, delay=0.1)
        self.assertTrue(connected)

        # Client sends telemetry
        sent = await client.send(
            Message(signal=SignalType.SIG_TELEMETRY, sender="Beta", payload={"data": 42})
        )
        self.assertTrue(sent)

        # Allow async event loop to process
        await asyncio.sleep(0.3)
        self.assertEqual(len(received_by_server), 1)
        self.assertEqual(received_by_server[0].payload.get("data"), 42)

        await client.disconnect()
        await server.stop()


if __name__ == "__main__":
    unittest.main()
