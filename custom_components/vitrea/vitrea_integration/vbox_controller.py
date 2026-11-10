# vbox_controller.py
import asyncio
import contextlib
import datetime
import logging
from collections.abc import Callable

from .control_api.commands import (
    AuthenticateCommand,
    GetControllerVersionCommand,
    GetFullStatusCommand,
)
from .control_api.responses import parse_response
from .parameter_api import VitreaDatabaseReaderV3 as VitreaDatabaseReader
from .utils.const import SUPPORTED_VERSIONS, UPGRADEABLE_VERSIONS
from .vbox_connection import VBoxConnection

_LOGGER = logging.getLogger(__name__)


class VBoxController:
    """
    High-level controller for Vitrea VBox system.

    Manages connection, database reading, status updates, and provides
    callback mechanisms for state changes. Coordinates between the connection
    layer and parameter API to provide a unified interface.

    Attributes:
        connection: VBoxConnection instance for low-level communication
        database: Loaded Vitrea database model
        _callbacks: Set of registered callback functions
    """

    def __init__(
        self,
        ip: str,
        port: int,
        event_beat_seconds: int = 0.02,
        thread_beat_seconds: int = 0.05,
        status_update_callback=None,
        enabled=True,
    ):
        self.connection = VBoxConnection(
            ip=ip,
            port=port,
            event_beat_seconds=event_beat_seconds,
            connection_callback=self._connection_change_callback,
            response_callback=self.on_response,
        )
        self.id = None
        self.communication_lock = asyncio.Lock()
        self.event_beat_seconds = event_beat_seconds
        self.vitrea_db_reader = None
        self.thread_beat_seconds = thread_beat_seconds
        self.parsing_loop = None
        self._callbacks = set()
        if status_update_callback is not None:
            self._callbacks.add(status_update_callback)
        self.enabled = enabled
        self._db_initialized = False
        self.database = None
        self.watchdog_task: asyncio.Task | None = None
        self.last_incoming_message: datetime.datetime | None = None
        self.response_handler_task: asyncio.Task | None = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=512)

    async def _connection_change_callback(self, connected):
        """Handle connection state changes."""
        await self.publish_updates({"type": "connection", "status": connected})
        if connected and self._db_initialized:
            await self.update_state()

    async def _health_check(self) -> bool:
        """Check if controller is healthy based on recent activity."""
        if not self.connection.is_healthy():
            return False
        if not self.last_incoming_message:
            return True
        if (
            datetime.datetime.now() - self.last_incoming_message
        ).total_seconds() > 50:
            return False
        if self.response_handler_task and self.response_handler_task.done():
            return False
        return True

    async def watchdog_loop(self):
        """Monitor controller health and reconnect if needed."""
        await asyncio.sleep(30)
        while self.enabled:
            if not await self._health_check():
                _LOGGER.warning(
                    "Vitrea Controller is not responding, requesting reconnect"
                )
                await self.connection.request_reconnect()
            if self.response_handler_task is None or self.response_handler_task.done():
                if self.response_handler_task and self.response_handler_task.exception():
                    _LOGGER.error(
                        "Response handler task crashed: %s",
                        self.response_handler_task.exception(),
                    )
                self.response_handler_task = asyncio.create_task(
                    self.response_thread_loop(),
                    name="vitrea-response-handler",
                )
            await asyncio.sleep(30)
        await self.connection.close()

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Switch changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self, *args, **kwargs) -> None:
        """Schedule call all registered callbacks."""
        for callback in self._callbacks:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)

    async def read_vitrea_db(self):
        """Read the Vitrea database from the controller."""
        if not self.connection.connected:
            success = await self.connection.connect()
            if not success:
                raise ConnectionError("Could not connect to Vitrea")
        self.vitrea_db_reader = VitreaDatabaseReader(write=self.connection.send)
        vitrea_db = await self.vitrea_db_reader.read_vitrea_controller(force=True)
        self.database = vitrea_db
        del self.vitrea_db_reader
        self.vitrea_db_reader = None
        self._db_initialized = True
        _LOGGER.debug("Vitrea database initialized")
        return self.database

    async def connect(self, ignore_db=False, watchdog=True):
        """Connect to the Vitrea controller and optionally load database."""
        self.enabled = True
        connected = await self.connection.connect()
        if not connected:
            raise ConnectionError("Could not connect to Vitrea")
        if self.response_handler_task is None or self.response_handler_task.done():
            self.response_handler_task = asyncio.create_task(
                self.response_thread_loop(),
                name="vitrea-response-handler",
            )
        if not self.database and not ignore_db:
            await self.read_vitrea_db()
            # No status sync here: the consumer requests it (update_state)
            # once its devices are registered, so the responses have
            # somewhere to land. Reconnects still resync automatically via
            # _connection_change_callback.
        if watchdog:
            self.watchdog_task = asyncio.create_task(self.watchdog_loop())

        return connected

    async def update_state(self):
        """Request full status update from the controller."""
        if self.connection.connected:
            await self.connection.send(GetFullStatusCommand().serialize())

    @staticmethod
    async def validate_controller_availability(
        ip: str, port: int, timeout: float = 5.0
    ) -> dict:
        """Check if the Vitrea Gateway is available and supported.

        Uses a short-lived asyncio connection with strict timeouts: the vBox
        accepts only a single host socket, so validation must never linger
        (and must not block the event loop).
        """
        result = {
            "supported": False,
            "reason": "",
            "version": "",
            "supports_led_commands": False,
        }
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port), timeout=timeout
            )

            frames_seen = 0

            async def scan_for(predicate, window: float):
                """Read frames for up to `window` seconds; return the first
                one matching predicate. Live systems push unsolicited status
                frames at any time, so the interesting frame is rarely the
                first one."""
                nonlocal frames_seen
                loop = asyncio.get_running_loop()
                deadline = loop.time() + window
                while (remaining := deadline - loop.time()) > 0:
                    try:
                        data = await asyncio.wait_for(
                            reader.readuntil(b"\r\n"), timeout=remaining
                        )
                    except asyncio.TimeoutError:
                        return None
                    frames_seen += 1
                    parsed = parse_response(data)
                    if isinstance(parsed, dict) and predicate(parsed):
                        return parsed
                return None

            def is_ack(parsed: dict) -> bool:
                return (
                    parsed.get("type") == "acknowledgment"
                    or parsed.get("subtype") == "keep_alive_acknowledgment"
                )

            # Firmware quirk (observed on 9.50): the very first P:VITREA on
            # a fresh socket is not always acknowledged, while every repeat
            # is — so retry the authentication a few times.
            ack = None
            auth_window = min(2.0, timeout)
            for _ in range(3):
                writer.write(AuthenticateCommand().serialize())
                await writer.drain()
                ack = await scan_for(is_ack, auth_window)
                if ack:
                    break
            if not ack:
                # Frames without an ack = the controller rejected us; total
                # silence = wrong host/port or an unresponsive controller.
                result["reason"] = "auth_failed" if frames_seen else "connection_error"
                return result

            writer.write(GetControllerVersionCommand().serialize())
            await writer.drain()
            parsed_response = await scan_for(
                lambda parsed: parsed.get("type") == "version", timeout
            )
            if parsed_response is None:
                result["reason"] = "connection_error"
                return result

            major_version = parsed_response.get("major_version", 0)
            minor_version = parsed_response.get("minor_version", 0)
            result["version"] = f"{major_version}.{minor_version}"
            if minor_version >= SUPPORTED_VERSIONS.get(major_version, 200):
                result["supported"] = True
            elif major_version in UPGRADEABLE_VERSIONS and (
                minor_version >= UPGRADEABLE_VERSIONS.get(major_version, 200)
            ):
                result["reason"] = "unsupported_version_upgrade_optional"
            else:
                result["reason"] = "unsupported_version"
            # LED indicator control (L command) shipped with firmware 9.50.
            result["supports_led_commands"] = major_version == 0 or (
                (major_version, minor_version) >= (9, 50)
            )
            _LOGGER.debug(result)
            return result
        except (ConnectionError, TimeoutError, OSError, asyncio.IncompleteReadError):
            result["reason"] = "connection_error"
        finally:
            # Free the vBox's single socket slot promptly on every path.
            if writer:
                writer.close()
                with contextlib.suppress(ConnectionError, OSError):
                    await writer.wait_closed()
        _LOGGER.debug(result)
        return result

    async def close(self):
        """Close the controller."""
        self.enabled = False
        if self.watchdog_task:
            self.watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.watchdog_task
            self.watchdog_task = None
        if self.response_handler_task:
            self.response_handler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.response_handler_task
            self.response_handler_task = None
        await self.connection.close()
        return True

    async def _validate_single_response(self, response: bytes):
        """Validate if response is a single message or multiple."""
        if not response.hex().startswith("5654483c"):
            possible_responses = response.decode("utf-8", errors="replace").split(
                "\r\n"
            )
            if len(possible_responses) > 1:
                return False
        return True

    async def _handle_multiple_messages(self, response: bytes):
        """Handle responses that contain multiple messages."""
        if not response.hex().startswith("5654483c"):
            possible_responses = response.decode("utf-8", errors="replace").split(
                "\r\n"
            )
            if len(possible_responses) == 1:
                return True
            else:
                for item in possible_responses:
                    if item:
                        await self.on_response(item.encode())
        return True

    async def on_response(self, response):
        """Handle incoming response from the controller in a threaded manner."""
        try:
            self._response_queue.put_nowait(response)
        except asyncio.QueueFull:
            _LOGGER.warning("Dropping response due to full queue")
        return True

    async def response_thread_loop(self):
        """Process controller responses sequentially, preserving arrival order.

        Sequential handling matters: spawning a task per message allowed two
        rapid status updates for the same key to be applied out of order.
        """
        while self.enabled:
            try:
                response = await asyncio.wait_for(
                    self._response_queue.get(), timeout=1
                )
            except asyncio.TimeoutError:
                continue
            try:
                await self._response_task(response)
            except Exception as err:  # noqa: BLE001 - keep the loop alive
                _LOGGER.warning("Response handler failed: %s", err, exc_info=err)

    async def _response_task(self, response):
        """Handle incoming response from the controller."""
        if not await self._validate_single_response(response):
            return await self._handle_multiple_messages(response)
        try:
            self.last_incoming_message = datetime.datetime.now()
            if response.hex().startswith("5654483c"):  # Params Received
                if self.vitrea_db_reader:
                    await self.vitrea_db_reader.feed(response)
            else:
                result = parse_response(response)
                if isinstance(result, dict):
                    result = [result]
                for item in result:
                    _LOGGER.debug("Parsed Response: %s", item)
                    if item.get("type") == "acknowledgment":
                        if item.get("subtype", "") == "keep_alive_acknowledgment":
                            self.connection.last_keep_alive = item.get("timestamp")
                    elif "status" in item.get("type", ""):
                        await self.publish_updates(item)
        except (TypeError, ValueError) as e:
            _LOGGER.error("Error parsing response", stack_info=True)
            _LOGGER.error("Response: %s", response.hex())
            _LOGGER.error(e)
            return False
        return True

    async def __aexit__(self, exc_type, exc, tb):
        """Close the controller."""
        await self.close()
        return True
