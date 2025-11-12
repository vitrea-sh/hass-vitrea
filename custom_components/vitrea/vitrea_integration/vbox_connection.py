import asyncio
import contextlib
import logging
import threading
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from .control_api.commands import AuthenticateCommand

_LOGGER = logging.getLogger(__name__)


def _create_task(awaitable: Awaitable[Any], *, name: str) -> asyncio.Task:
    """Create background tasks with a common exception handler."""

    task = asyncio.create_task(awaitable, name=name)

    def _log_task_result(task: asyncio.Task) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            if exception := task.exception():
                _LOGGER.error(
                    "Task %s crashed: %s", task.get_name(), exception, exc_info=exception
                )

    task.add_done_callback(_log_task_result)
    return task


class VBoxConnection:
    """Manage the socket connection to a Vitrea VBox controller."""

    def __init__(
        self,
        ip: str,
        port: int,
        response_callback: Callable,
        connection_callback: Callable | None = None,
        event_beat_seconds: int = 0.2,
        enabled=True,
    ) -> None:
        self.ip = ip
        self.port = port
        self.reader = None
        self.writer = None
        self.command_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self.event_beat_seconds = event_beat_seconds
        self._connected = False
        self._last_keep_alive = None
        self.response_callback = response_callback
        self.connection_callback = connection_callback
        self.enabled = enabled
        self.error_reason = "Unknown Error"
        self.last_keep_alive_sent = None
        self._connected_lock = threading.Lock()
        self._task_lock = threading.Lock()
        # Timestamps and diagnostics
        self.last_rx = None
        self.last_tx = None
        # Reconnect coordination
        self._reconnect_lock = asyncio.Lock()
        self.reconnecting = False
        self._unavailable_logged = False
        # Connection lifecycle
        self._connect_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._reader_task: asyncio.Task | None = None
        self._writer_task: asyncio.Task | None = None
        self._monitor_task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()

    @property
    def connected(self):
        """Return the connection status of the VBox."""
        with self._connected_lock:
            return self._connected

    @property
    def last_keep_alive(self):
        """Return the timestamp of the last keep alive message."""
        return self._last_keep_alive

    @last_keep_alive.setter
    def last_keep_alive(self, timestamp):
        """Set the last keep alive timestamp."""
        self._last_keep_alive = timestamp

    async def set_connected(self, value):
        """Set the connected property and notify on transitions."""
        changed = False
        with self._connected_lock:
            if self._connected != value:
                self._connected = value
                changed = True
        if changed:
            # Once-only availability logging
            if value:
                if self._unavailable_logged:
                    _LOGGER.info("The connection is back online")
                self._unavailable_logged = False
            elif not self._unavailable_logged:
                _LOGGER.info("The connection is unavailable: %s", self.error_reason)
                self._unavailable_logged = True
            await self._update_connection_state(value)

    async def _update_connection_state(self, value):
        """Update connection state and notify callback if set."""
        if self.connection_callback:
            await self.connection_callback(value)

    def _response_task_callback(self, task: asyncio.Task):
        try:
            task.result()
            self.response_tasks.remove(task)
        except Exception as e:
            task_stack = task.get_stack()
            _LOGGER.warning(e, stack_info=task_stack, exc_info=True)

    async def connect(self, reconnect=False):
        """Ensure a single active connection to the VBox controller."""

        if not reconnect:
            self.enabled = True

        async with self._connect_lock:
            if self.connected and self.reader and self.writer:
                return True

            await self._open_connection()
            if not self.connected:
                raise ConnectionError(
                    f"Failed to connect to VBox at {self.ip}:{self.port}"
                )
            self._stop_event.clear()
            await self._send_keep_alive()
            self._ensure_background_tasks()

        async with self._reconnect_lock:
            self.reconnecting = False

        await self._update_connection_state(self.connected)
        return True

    async def request_reconnect(self) -> None:
        """Schedule a reconnect if not already in progress."""
        async with self._reconnect_lock:
            if self.reconnecting or not self.enabled:
                return
            self.reconnecting = True
            reconnect_task = _create_task(self.reconnect(), name="vitrea-reconnect")
            reconnect_task.add_done_callback(lambda task: self._tasks.discard(task))
            self._tasks.add(reconnect_task)

    async def reconnect(self):
        """Reconnect to the VBox with exponential backoff; single-flight guarded."""
        async with self._reconnect_lock:
            if not self.enabled:
                self.reconnecting = False
                return False
            # Ensure flag is set
            self.reconnecting = True
        _LOGGER.warning("Connection to Vitrea lost due to: %s", self.error_reason)
        await self.close(disable=False)

        attempts = 0
        max_attempts = 10
        base_delay = 1.0

        while attempts < max_attempts:
            attempts += 1
            delay = min(30, base_delay * (2 ** (attempts - 1)))

            try:
                if not self.enabled:
                    break

                _LOGGER.debug(
                    "Reconnection attempt #%s to VBox after %ss delay", attempts, delay
                )
                success = await self.connect(reconnect=True)

                if success:
                    _LOGGER.info(
                        "Successfully reconnected to VBox - attempt #%s", attempts
                    )
                    return True

            except Exception as e:  # noqa: BLE001
                _LOGGER.error("Reconnection attempt #%s failed: %s", attempts, e)

            await self._teardown_connection(disable=False)
            await self._update_connection_state(False)
            await asyncio.sleep(delay)

        _LOGGER.error("Failed to reconnect after %s attempts, giving up", max_attempts)
        async with self._reconnect_lock:
            self.reconnecting = False
        return False

    async def send(self, command: bytes):
        """Add a command to the queue to be sent to the VBox. If the connection is lost, reconnect."""
        if not self.connected or not self.writer:
            await self.set_connected(False)
            self.error_reason = "Send Failed"
            await self.request_reconnect()
            return False
        if not isinstance(command, bytes):
            raise TypeError("Command must be bytes, received str:", command)
        await self.command_queue.put(command)
        return True

    async def receive(self):
        """Get the next response from the VBox."""
        if not self.connected:
            return None
        if not self.reader:
            return None
        # Responses are pushed via callback, kept for backwards compatibility.
        return None

    async def close(self, disable=True):
        """Close the connection to the VBox."""
        await self._teardown_connection(disable=disable)
        return True

    @property
    def is_connected(self):
        """Return if the connection is established."""
        return self.connected

    async def _open_connection(self) -> bool:
        """Establish a fresh TCP connection to the controller."""

        await self._close_writer()

        for attempt in range(1, 4):
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=3
                )
                _LOGGER.info("Connected to VBox")
                await self.set_connected(True)
                self.last_keep_alive = None
                return True
            except (ConnectionError, TimeoutError) as exc:
                _LOGGER.error(
                    "Connection attempt %s to VBox at %s:%s failed: %s",
                    attempt,
                    self.ip,
                    self.port,
                    exc,
                )
                self.error_reason = "Connection Failed"
                await self.set_connected(False)
                await asyncio.sleep(1)

        raise ConnectionError(f"Failed to connect to VBox at {self.ip}:{self.port}")

    async def _send_keep_alive(self) -> None:
        """Send a keep-alive command."""

        if not self.writer:
            return
        await self._send(AuthenticateCommand().serialize())
        self.last_keep_alive_sent = datetime.now()

    def _ensure_background_tasks(self) -> None:
        """Spawn the reader/writer/monitor tasks exactly once."""

        with self._task_lock:
            if self._reader_task is None or self._reader_task.done():
                self._reader_task = _create_task(
                    self._reader_loop(), name="vitrea-reader"
                )
                self._reader_task.add_done_callback(
                    lambda task: self._tasks.discard(task)
                )
                self._tasks.add(self._reader_task)

            if self._writer_task is None or self._writer_task.done():
                self._writer_task = _create_task(
                    self._writer_loop(), name="vitrea-writer"
                )
                self._writer_task.add_done_callback(
                    lambda task: self._tasks.discard(task)
                )
                self._tasks.add(self._writer_task)

            if self._monitor_task is None or self._monitor_task.done():
                self._monitor_task = _create_task(
                    self._monitor_loop(), name="vitrea-monitor"
                )
                self._monitor_task.add_done_callback(
                    lambda task: self._tasks.discard(task)
                )
                self._tasks.add(self._monitor_task)

    def _tasks_running(self) -> bool:
        return any(task for task in self._tasks if not task.done())

    async def _reader_loop(self) -> None:
        """Continuously read messages from the controller."""

        while self.enabled and not self._stop_event.is_set():
            response = await self._receive()
            if not response:
                if not self.connected:
                    await self._handle_connection_failure()
                    return
                await asyncio.sleep(self.event_beat_seconds)
                continue

            self.last_rx = datetime.now()
            if response.startswith((b"VTH>", b"H:")):
                _LOGGER.debug("Dropping echo frame: %s", response)
                continue

            _LOGGER.debug(
                "Received response from VBox: %s (hex: %s)", response, response.hex()
            )
            try:
                await self.response_callback(response)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Response callback failed: %s", err, exc_info=err)

        _LOGGER.debug("Reader loop finished")

    async def _writer_loop(self) -> None:
        """Continuously send queued commands to the controller."""

        while self.enabled and not self._stop_event.is_set():
            try:
                command = await asyncio.wait_for(
                    self.command_queue.get(), timeout=self.event_beat_seconds
                )
            except asyncio.TimeoutError:
                command = None

            if not command:
                continue
            await self._send(command)
            continue 

        _LOGGER.debug("Writer loop finished")

    async def _monitor_loop(self) -> None:
        """Monitor connection state and trigger keep-alives/timeouts."""

        while self.enabled and not self._stop_event.is_set():
            now = datetime.now()
            if (
                self.last_keep_alive_sent is None
                or (now - self.last_keep_alive_sent) > timedelta(seconds=20)
            ):
                try:
                    await self._send_keep_alive()
                except ConnectionError as exc:
                    _LOGGER.error("Failed to send keep alive: %s", exc)
                    self.error_reason = "Keep Alive Send Failed"
                    await self._handle_connection_failure()
                    return

            if self.last_rx and (now - self.last_rx) > timedelta(seconds=45):
                _LOGGER.error(
                    "No keep alive response received for more than 45 seconds"
                )
                self.error_reason = "Keep Alive Timeout"
                await self._handle_connection_failure()
                return

            await asyncio.sleep(max(self.event_beat_seconds, 0.5))

        _LOGGER.debug("Monitor loop finished")

    async def _send(self, command: bytes) -> bool:
        """Send a command to the VBox."""
        _LOGGER.debug(("sending(ascii):", command))
        _LOGGER.debug(("sending(hex):", command.hex()))
        if not self.writer:
            raise ConnectionError("Connection is not available")
        self.writer.write(command)
        await self.writer.drain()
        self.last_tx = datetime.now()
        _LOGGER.debug("Command sent to VBox")
        return True

    async def _receive(self):
        """Receive a response from the VBox."""
        if not self.reader or not self.writer:
            await self.set_connected(False)
            self.error_reason = "Connection Lost"
            return None
        prefix = await self.reader.read(2)
        # prefix should be b'VT' and we should remove the newline before combining with data.
        if prefix != b"VT":
            result = await self.reader.readuntil(b"\r\n")
            result = prefix + result
        else:
            info = await self.reader.read(5)
            # len is 2 bytes at the end of the info
            length = int(info[-2:].hex()[1:], 16)
            result = await self.reader.read(length)
            result = prefix + info + result
        if not result:
            self.error_reason = "Connection Closed By Controller"
            await self.set_connected(False)
        if result:
            _LOGGER.debug(("RECEIVED: ", result.hex()))
        return result

    async def __aexit__(self, exc_type, exc, tb):
        """Close the connection when exiting async context."""
        await self.close()
        return True

    async def _handle_connection_failure(self) -> None:
        """Handle connection failures by shutting down tasks and reconnecting."""

        self._stop_event.set()
        await self.set_connected(False)
        await self._close_writer()
        await self._update_connection_state(False)
        await self.request_reconnect()

    async def _teardown_connection(self, *, disable: bool) -> None:
        """Cancel background tasks and close the socket."""

        if disable:
            self.enabled = False

        self._stop_event.set()
        with self._task_lock:
            current = asyncio.current_task()
            for task in list(self._tasks):
                if task is current:
                    continue
                task.cancel()
            for task in list(self._tasks):
                if task is current:
                    continue
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self._tasks.clear()
            self._reader_task = None
            self._writer_task = None
            self._monitor_task = None

        await self._close_writer()

        await self.set_connected(False)
        await self._update_connection_state(False)

    async def _close_writer(self) -> None:
        """Close the current writer if one exists."""

        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            self.reader = None
            self.writer = None
            _LOGGER.info("Disconnected from VBox")

    def is_healthy(self) -> bool:
        """Return True when the active connection and tasks look healthy."""

        if not self.connected:
            return False
        if self.last_rx and datetime.now() - self.last_rx > timedelta(seconds=45):
            return False
        for task in (self._reader_task, self._writer_task, self._monitor_task):
            if task and task.done():
                return False
        return True
