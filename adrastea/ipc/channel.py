import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional
from .protocol import Message, SignalType

logger = logging.getLogger("Adrastea.IPC")
HandlerType = Callable[[Message], Coroutine[Any, Any, Optional[Message]]]


class IPCServer:
    """IPC Server hosted by System Alpha to communicate with Beta."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.clients: List[asyncio.StreamWriter] = []
        self.handlers: Dict[SignalType, List[HandlerType]] = {}
        self._running = False

    def register_handler(self, signal: SignalType, handler: HandlerType) -> None:
        if signal not in self.handlers:
            self.handlers[signal] = []
        self.handlers[signal].append(handler)

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
        self._running = True
        logger.info(f"Alpha IPC Server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        self._running = False
        for writer in self.clients:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self.clients.clear()
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("Alpha IPC Server stopped.")

    async def broadcast(self, message: Message) -> None:
        """Send a message to all connected clients (Beta)."""
        data = message.to_json().encode("utf-8")
        dead_clients = []
        for writer in self.clients:
            try:
                writer.write(data)
                await writer.drain()
            except Exception as e:
                logger.warning(f"Error broadcasting to client: {e}")
                dead_clients.append(writer)
        for dead in dead_clients:
            if dead in self.clients:
                self.clients.remove(dead)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.clients.append(writer)
        addr = writer.get_extra_info("peername")
        logger.info(f"IPC Client connected: {addr}")

        buffer = ""
        try:
            while self._running:
                data = await reader.read(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        try:
                            msg = Message.from_json(line)
                            await self._dispatch(msg, writer)
                        except Exception as e:
                            logger.error(f"Error parsing IPC message '{line}': {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Client connection closed with error: {e}")
        finally:
            if writer in self.clients:
                self.clients.remove(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"IPC Client disconnected: {addr}")

    async def _dispatch(self, msg: Message, writer: asyncio.StreamWriter) -> None:
        handlers = self.handlers.get(msg.signal, [])
        for handler in handlers:
            try:
                resp = await handler(msg)
                if resp:
                    if "reply_to" not in resp.payload:
                        resp.payload["reply_to"] = msg.message_id
                    writer.write(resp.to_json().encode("utf-8"))
                    await writer.drain()
            except Exception as e:
                logger.error(f"Error executing IPC handler for {msg.signal}: {e}")


class IPCClient:
    """IPC Client used by System Beta and Keep-Alive processes to connect to System Alpha."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.handlers: Dict[SignalType, List[HandlerType]] = {}
        self._running = False
        self._listener_task: Optional[asyncio.Task] = None
        self._pending_queries: Dict[str, asyncio.Future] = {}
        self._pending_signal_waiters: Dict[SignalType, List[asyncio.Future]] = {}

    def register_handler(self, signal: SignalType, handler: HandlerType) -> None:
        if signal not in self.handlers:
            self.handlers[signal] = []
        self.handlers[signal].append(handler)

    async def connect(self, retries: int = 5, delay: float = 1.0) -> bool:
        for attempt in range(retries):
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self._running = True
                self._listener_task = asyncio.create_task(self._listen_loop())
                logger.info(f"Connected to Alpha IPC Server at {self.host}:{self.port}")
                return True
            except Exception as e:
                logger.debug(f"IPC connect attempt {attempt + 1}/{retries} failed: {e}")
                await asyncio.sleep(delay)
        return False

    async def disconnect(self) -> None:
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
        # Cancel any pending queries
        for fut in list(self._pending_queries.values()):
            if not fut.done():
                fut.cancel()
        self._pending_queries.clear()
        self._pending_signal_waiters.clear()
        logger.info("Disconnected from Alpha IPC.")

    async def send(self, message: Message) -> bool:
        if not self.writer or not self._running:
            return False
        try:
            self.writer.write(message.to_json().encode("utf-8"))
            await self.writer.drain()
            return True
        except Exception as e:
            logger.error(f"Failed to send message {message.signal}: {e}")
            return False

    async def query(self, message: Message, timeout: float = 5.0) -> Optional[Message]:
        """Send a message and await a matching response via IPC."""
        if not self.writer or not self._running:
            return None
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_queries[message.message_id] = future

        # Also register by signal in case responder doesn't preserve message_id
        sig = message.signal
        if sig not in self._pending_signal_waiters:
            self._pending_signal_waiters[sig] = []
        self._pending_signal_waiters[sig].append(future)

        if not await self.send(message):
            self._pending_queries.pop(message.message_id, None)
            if sig in self._pending_signal_waiters and future in self._pending_signal_waiters[sig]:
                self._pending_signal_waiters[sig].remove(future)
            return None

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_queries.pop(message.message_id, None)
            if sig in self._pending_signal_waiters and future in self._pending_signal_waiters[sig]:
                self._pending_signal_waiters[sig].remove(future)

    async def _listen_loop(self) -> None:
        buffer = ""
        try:
            while self._running and self.reader:
                data = await self.reader.read(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        try:
                            msg = Message.from_json(line)
                            # Check pending queries by reply_to
                            reply_to = msg.payload.get("reply_to")
                            resolved = False
                            if reply_to and reply_to in self._pending_queries:
                                fut = self._pending_queries.pop(reply_to)
                                if not fut.done():
                                    fut.set_result(msg)
                                    resolved = True

                            # Check pending signal waiters if not resolved
                            if not resolved and msg.signal in self._pending_signal_waiters:
                                waiters = self._pending_signal_waiters[msg.signal]
                                while waiters:
                                    w_fut = waiters.pop(0)
                                    if not w_fut.done():
                                        w_fut.set_result(msg)
                                        break

                            handlers = self.handlers.get(msg.signal, [])
                            for handler in handlers:
                                await handler(msg)
                        except Exception as e:
                            logger.error(f"Error handling message in client: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Client listener encountered error: {e}")
        finally:
            self._running = False
