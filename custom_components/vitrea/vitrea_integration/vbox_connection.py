import asyncio
import logging
import threading
from datetime import datetime, timedelta
from collections.abc import Callable
import contextlib

from .control_api.commands import AuthenticateCommand

_LOGGER = logging.getLogger(__name__)


class VBoxConnection:
    """
    Manage connection to Vitrea VBox controller.

    Handles asynchronous communication with the VBox including connection
    management, command queuing, response handling, and automatic reconnection
    with exponential backoff.

    Attributes:
        ip: IP address of the VBox
        port: Port number for connection
        response_callback: Callback function for handling responses
        connection_callback: Optional callback for connection state changes
        event_beat_seconds: Time interval for communication loop
        enabled: Whether the connection is enabled
    """

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
        self.command_queue = asyncio.Queue()
        self.response_queue = asyncio.Queue()
        self.event_beat_seconds = event_beat_seconds
        self._connected = False
        self.communication_task = None
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
        """Connect to the VBox."""
        if not reconnect:
            self.enabled = True
        if not self.reader or not self.writer or not self.connected:
            await self._connect()
            if not self.connected:
                raise ConnectionError(
                    f"Failed to connect to VBox at {self.ip}:{self.port}"
                )
            await self._send_keep_alive()
        with self._task_lock:
            if self.communication_task is None or self.communication_task.done():
                self.communication_task = asyncio.create_task(
                    self._communication_loop()
                )
        # Reset reconnecting flag on successful connect
        async with self._reconnect_lock:
            self.reconnecting = False
        # Notify state
        await self._update_connection_state(self.connected)
        return True

    async def request_reconnect(self) -> None:
        """Schedule a reconnect if not already in progress."""
        async with self._reconnect_lock:
            if self.reconnecting or not self.enabled:
                return
            self.reconnecting = True
            if self.communication_task is None or self.communication_task.done():
                self.communication_task = asyncio.create_task(self.reconnect())

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

            await self.close(disable=False)
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
            # Check if com task is dropped
            with self._task_lock:
                if self.communication_task is None or self.communication_task.done():
                    await self.request_reconnect()
            return False
        if not isinstance(command, bytes):
            raise TypeError("Command must be bytes, received str:", command)
        await self.command_queue.put(command)
        return True

    async def receive(self):
        """Get the next response from the VBox."""
        if not self.response_queue.empty():
            response = await self.response_queue.get()
            return response
        return None

    async def close(self, disable=True):
        """Close the connection to the VBox."""
        if disable:
            self.enabled = False
            await self._update_connection_state(False)
            if self.communication_task:
                self.communication_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self.communication_task
        try:
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        self.writer = None
        _LOGGER.info("Disconnected from VBox")
        await self.set_connected(False)
        await self._update_connection_state(False)
        return True

    @property
    def is_connected(self):
        """Return if the connection is established."""
        return self.connected

    async def _connect(self) -> bool:
        """Establish connection to VBox with retry logic."""
        # Try connecting 3 times, if it fails - raise an exception
        for _ in range(3):
            try:
                self.reader, self.writer = await asyncio.wait_for(
                    asyncio.open_connection(self.ip, self.port), timeout=3
                )
                _LOGGER.info("Connected to VBox")
                await self.set_connected(True)
                self.last_keep_alive = None
                return True
            except (ConnectionError, TimeoutError):
                _LOGGER.error(
                    "Connection to VBox at %s:%s failed, retrying",
                    self.ip,
                    str(self.port),
                )
                self.error_reason = "Connection Failed"
                await self.set_connected(False)
                await asyncio.sleep(1)
        raise ConnectionError(f"Failed to connect to VBox at {self.ip}:{self.port}")

    async def _send_keep_alive(self):
        """Send keep-alive message to VBox."""
        await self._send(AuthenticateCommand().serialize())
        self.last_keep_alive_sent = datetime.now()

    async def _communication_loop(self):
        """Main communication loop handling send/receive operations."""
        while True:
            if not self.enabled:
                return
            if (datetime.now() - self.last_keep_alive_sent) > timedelta(seconds=20):
                await self._send_keep_alive()
            if not self.connected:
                break
            # Handle Keep Alive
            if self.last_keep_alive:
                if datetime.now() - self.last_keep_alive > timedelta(seconds=45):
                    _LOGGER.error(
                        "No keep alive response received for more than 40 seconds, reconnecting"
                    )
                    self.error_reason = "Keep Alive Timeout"
                    await self.set_connected(False)
                    break
            # Send Commands In Queue
            if not self.command_queue.empty():
                command = await self.command_queue.get()
                try:
                    success = await asyncio.wait_for(
                        self._send(command), timeout=self.event_beat_seconds
                    )
                    if not success:
                        _LOGGER.error("Sending command to VBox failed, reconnecting")
                        self.error_reason = "Command Send Failed"
                        await self.set_connected(False)
                        break
                except TimeoutError:
                    _LOGGER.error(
                        "Sending command to VBox took longer than expected, reconnecting"
                    )
                    self.error_reason = "Command Send Timeout"
                    await self.set_connected(False)
                    break
                except ConnectionError:
                    _LOGGER.error(
                        "Connection to VBox lost while sending command, reconnecting"
                    )
                    self.error_reason = "Connection Lost On Send"
                    await self.set_connected(False)
                    break
            # Receive Incoming Message
            try:
                response = await asyncio.wait_for(
                    self._receive(), timeout=self.event_beat_seconds / 2
                )
            except (TimeoutError, asyncio.CancelledError):
                response = None
            # Handle Incoming Message
            if response:
                _LOGGER.debug(
                    "Received response from VBox: %s (hex: %s)",
                    response,
                    response.hex(),
                )
                # Update last_rx
                self.last_rx = datetime.now()
                # Drop echoed frames; do not enqueue into outbound queue
                if response.startswith((b"VTH>", b"H:")):
                    _LOGGER.debug("Dropping echo frame: %s", response)
                else:
                    _LOGGER.debug("Calling response_callback with: %s", response.hex())
                    await self.response_callback(response)
            else:
                pass
        await self.request_reconnect()

    async def _send(self, command: bytes) -> bool:
        """Send a command to the VBox."""
        _LOGGER.debug(("sending(ascii):", command))
        _LOGGER.debug(("sending(hex):", command.hex()))
        self.writer.write(command)
        await self.writer.drain()
        self.last_tx = datetime.now()
        return True

    async def _receive(self):
        """Receive a response from the VBox."""
        if not self.reader or not self.writer:
            await self.set_connected(False)
            self.error_reason = "Connection Lost"
            return None
        try:
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
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            result = None
        except (ConnectionAbortedError, ConnectionResetError):
            self.error_reason = "Connection with VBox Lost"
            await self.set_connected(False)
            result = None
        if result:
            _LOGGER.debug(("RECEIVED: ", result.hex()))
        return result

    async def __aexit__(self, exc_type, exc, tb):
        """Close the connection when exiting async context."""
        await self.close()
        return True
