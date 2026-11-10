import asyncio
import contextlib
import logging
import threading
import time
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

    # Parameter API frames are small (names, id lists); anything larger means
    # the stream is desynced and the connection must be reset.
    MAX_FRAME_LENGTH = 4096

    def __init__(
        self,
        ip: str,
        port: int,
        response_callback: Callable,
        connection_callback: Callable | None = None,
        event_beat_seconds: float = 0.2,
        enabled=True,
        keep_alive_interval: float = 20.0,
        rx_timeout: float = 45.0,
        reconnect_base_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
        connect_retry_delay: float = 1.0,
        command_ack_timeout: float = 1.0,
        max_command_age: float = 10.0,
    ) -> None:
        self.ip = ip
        self.port = port
        self.keep_alive_interval = keep_alive_interval
        self.rx_timeout = rx_timeout
        self.reconnect_base_delay = reconnect_base_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.connect_retry_delay = connect_retry_delay
        self.command_ack_timeout = command_ack_timeout
        self.max_command_age = max_command_age
        self.reader = None
        self.writer = None
        self.command_queue: asyncio.Queue[tuple[float, bytes]] = asyncio.Queue()
        self._ack_event = asyncio.Event()
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
        """Reconnect to the VBox with capped exponential backoff.

        Single-flight guarded; retries until it succeeds or the connection is
        disabled, so a long controller/network outage never leaves the
        connection permanently dead.
        """
        async with self._reconnect_lock:
            if not self.enabled:
                self.reconnecting = False
                return False
            # Ensure flag is set
            self.reconnecting = True
        _LOGGER.warning("Connection to Vitrea lost due to: %s", self.error_reason)
        await self.close(disable=False)

        attempts = 0
        try:
            while self.enabled:
                attempts += 1
                delay = min(
                    self.reconnect_max_delay,
                    self.reconnect_base_delay * (2 ** min(attempts - 1, 10)),
                )

                try:
                    _LOGGER.debug(
                        "Reconnection attempt #%s to VBox after %ss delay",
                        attempts,
                        delay,
                    )
                    if await self.connect(reconnect=True):
                        _LOGGER.info(
                            "Successfully reconnected to VBox - attempt #%s", attempts
                        )
                        return True
                except Exception as e:  # noqa: BLE001
                    # Warn once, then go quiet: reconnection may run for hours
                    # during an outage and must not flood the log.
                    _LOGGER.log(
                        logging.WARNING if attempts == 1 else logging.DEBUG,
                        "Reconnection attempt #%s failed: %s",
                        attempts,
                        e,
                    )

                await self._teardown_connection(disable=False)
                await asyncio.sleep(delay)
        finally:
            async with self._reconnect_lock:
                if not self.connected:
                    self.reconnecting = False
        return False

    async def send(self, command: bytes):
        """Queue a command for the VBox.

        Commands are queued even while disconnected (and a reconnect is
        requested), so a user action during a short blip is delivered once
        the link is back instead of silently vanishing. The writer drops
        commands older than max_command_age.
        """
        if not isinstance(command, bytes):
            raise TypeError("Command must be bytes, received str:", command)
        await self.command_queue.put((time.monotonic(), command))
        if not self.connected or not self.writer:
            self.error_reason = "Send Failed"
            await self.request_reconnect()
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
                # Arm the receive-staleness watchdog from the moment the
                # socket opens, so a connection that never receives anything
                # (half-open socket) still times out instead of going zombie.
                self.last_rx = datetime.now()
                return True
            except (ConnectionError, TimeoutError) as exc:
                # The caller reports the outcome once (setup error or the
                # reconnect loop's single warning); per-attempt detail would
                # flood the log during an outage.
                _LOGGER.debug(
                    "Connection attempt %s to VBox at %s:%s failed: %s",
                    attempt,
                    self.ip,
                    self.port,
                    exc,
                )
                self.error_reason = "Connection Failed"
                await self.set_connected(False)
                await asyncio.sleep(self.connect_retry_delay)

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

    async def _reader_loop(self) -> None:
        """Continuously read messages from the controller."""

        while self.enabled and not self._stop_event.is_set():
            try:
                response = await self._receive()
            except Exception as err:  # noqa: BLE001 - any read failure resets the link
                _LOGGER.warning("Reader failed, resetting connection: %s", err)
                self.error_reason = "Receive Failed"
                await self._handle_connection_failure()
                return
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
            # Any complete frame from the vBox unblocks the writer's pacing
            # wait (spec: send next only after an answer). Deliberately
            # broad: a single-key status request is answered with the status
            # frame itself and no OK, and any inbound traffic proves the
            # controller is alive and processing.
            self._ack_event.set()

            _LOGGER.debug("RX %s", response)
            try:
                await self.response_callback(response)
            except Exception as err:  # noqa: BLE001
                _LOGGER.error("Response callback failed: %s", err, exc_info=err)

        _LOGGER.debug("Reader loop finished")

    async def _writer_loop(self) -> None:
        """Continuously send queued commands to the controller."""

        while self.enabled and not self._stop_event.is_set():
            try:
                queued_at, command = await asyncio.wait_for(
                    self.command_queue.get(), timeout=self.event_beat_seconds
                )
            except asyncio.TimeoutError:
                continue

            age = time.monotonic() - queued_at
            if age > self.max_command_age:
                _LOGGER.warning(
                    "Dropping command queued %.1fs ago (max %.1fs): %s",
                    age,
                    self.max_command_age,
                    command,
                )
                continue
            self._ack_event.clear()
            try:
                await self._send(command)
            except (ConnectionError, OSError) as exc:
                _LOGGER.warning("Failed to send command, resetting connection: %s", exc)
                self.error_reason = "Send Failed"
                await self._handle_connection_failure()
                return
            # Spec recommendation: send the next command only after the vBox
            # answered the previous one. Cap the wait so a missing ack can
            # never stall the queue.
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._ack_event.wait(), timeout=self.command_ack_timeout
                )

        _LOGGER.debug("Writer loop finished")

    async def _monitor_loop(self) -> None:
        """Monitor connection state and trigger keep-alives/timeouts."""

        poll = max(self.event_beat_seconds, min(0.5, self.rx_timeout / 5))
        while self.enabled and not self._stop_event.is_set():
            now = datetime.now()
            if (
                self.last_keep_alive_sent is None
                or (now - self.last_keep_alive_sent)
                > timedelta(seconds=self.keep_alive_interval)
            ):
                try:
                    await self._send_keep_alive()
                except (ConnectionError, OSError) as exc:
                    _LOGGER.error("Failed to send keep alive: %s", exc)
                    self.error_reason = "Keep Alive Send Failed"
                    await self._handle_connection_failure()
                    return

            if self.last_rx and (now - self.last_rx) > timedelta(
                seconds=self.rx_timeout
            ):
                _LOGGER.error(
                    "No data received for more than %s seconds", self.rx_timeout
                )
                self.error_reason = "Keep Alive Timeout"
                await self._handle_connection_failure()
                return

            await asyncio.sleep(poll)

        _LOGGER.debug("Monitor loop finished")

    async def _send(self, command: bytes) -> bool:
        """Send a command to the VBox."""
        if not self.writer:
            raise ConnectionError("Connection is not available")
        _LOGGER.debug("TX %s", command)
        self.writer.write(command)
        await self.writer.drain()
        self.last_tx = datetime.now()
        return True

    async def _receive(self):
        """Receive a single framed response from the VBox.

        Uses exact reads so TCP fragmentation cannot desync the stream.
        Returns None when the connection is no longer usable; the reader
        loop turns that into a reconnect.
        """
        if not self.reader or not self.writer:
            await self.set_connected(False)
            self.error_reason = "Connection Lost"
            return None
        try:
            prefix = await self.reader.readexactly(2)
            if prefix != b"VT":
                # ASCII message, terminated by CR LF.
                result = prefix + await self.reader.readuntil(b"\r\n")
            else:
                # Binary parameter API frame: VTH< C# len(2 bytes, Hi-Lo) payload.
                info = await self.reader.readexactly(5)
                length = int.from_bytes(info[-2:], "big")
                if length > self.MAX_FRAME_LENGTH:
                    raise ValueError(f"Frame length {length} exceeds maximum")
                result = prefix + info + await self.reader.readexactly(length)
        except asyncio.IncompleteReadError:
            self.error_reason = "Connection Closed By Controller"
            await self.set_connected(False)
            return None
        except (ConnectionError, OSError) as exc:
            _LOGGER.warning("Receive failed: %s", exc)
            self.error_reason = "Connection Lost"
            await self.set_connected(False)
            return None
        except (asyncio.LimitOverrunError, ValueError) as exc:
            _LOGGER.warning("Framing error, resetting connection: %s", exc)
            self.error_reason = "Framing Error"
            await self.set_connected(False)
            return None
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
        await self.request_reconnect()

    async def _teardown_connection(self, *, disable: bool) -> None:
        """Cancel background tasks and close the socket."""

        if disable:
            self.enabled = False
            # Deliberate shutdown: don't report it as "Unknown Error".
            self.error_reason = "Connection Closed"

        self._stop_event.set()
        current = asyncio.current_task()
        # Snapshot and cancel under the lock, but never await while holding
        # it: _ensure_background_tasks takes the same blocking lock, so an
        # await here could freeze the entire event loop.
        with self._task_lock:
            tasks = [task for task in self._tasks if task is not current]
            for task in tasks:
                task.cancel()
            self._tasks.clear()
            self._reader_task = None
            self._writer_task = None
            self._monitor_task = None
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await self._close_writer()

        await self.set_connected(False)

    async def _close_writer(self) -> None:
        """Close the current writer if one exists."""

        had_writer = self.writer is not None
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            self.reader = None
            self.writer = None
            if had_writer:
                _LOGGER.info("Disconnected from VBox")

    def is_healthy(self) -> bool:
        """Return True when the active connection and tasks look healthy."""

        if not self.connected:
            return False
        if self.last_rx and datetime.now() - self.last_rx > timedelta(
            seconds=self.rx_timeout
        ):
            return False
        for task in (self._reader_task, self._writer_task, self._monitor_task):
            if task and task.done():
                return False
        return True
