# vbox_controller.py
import datetime
import socket
from typing import Any
from collections.abc import Callable
from .vbox_connection import VBoxConnection
from .control_api.responses import parse_response
from .control_api.commands import (
    GetControllerVersionCommand,
    AuthenticateCommand,
    GetFullStatusCommand,
)
from .parameter_api import VitreaDatabaseReaderV3 as VitreaDatabaseReader
from .utils.const import SUPPORTED_VERSIONS
import logging
import asyncio

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
        self.watchdog_task = None
        self.last_incoming_message = None
        self.response_handler_thread = None
        self.response_queue = []
        self.response_handler_task = None

    async def _connection_change_callback(self, connected):
        """Handle connection state changes."""
        await self.publish_updates({"type": "connection", "status": connected})
        if connected and self._db_initialized:
            await self.update_state()

    async def _health_check(self) -> bool:
        """Check if controller is healthy based on recent activity."""
        if not self.last_incoming_message:
            return False
        if (datetime.datetime.now() - self.last_incoming_message).seconds > 50:
            return False
        if self.connection.communication_task.done():
            return False
        if self.response_handler_thread and self.response_handler_thread.done():
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
                if (
                    self.response_handler_task
                    and self.response_handler_task.exception()
                ):
                    _LOGGER.error(
                        "Response handler task crashed: %s",
                        self.response_handler_task.exception(),
                    )
                self.response_handler_task = asyncio.create_task(
                    self.response_thread_loop()
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
                self.response_thread_loop()
            )
        if not self.database and not ignore_db:
            await self.read_vitrea_db()
        if watchdog:
            self.watchdog_task = asyncio.create_task(self.watchdog_loop())

        return connected

    async def update_state(self):
        """Request full status update from the controller."""
        if self.connection.connected:
            await self.connection.send(GetFullStatusCommand().serialize())

    @staticmethod
    async def validate_controller_availability(ip: str, port: int) -> dict:
        """Check if the Vitrea Gateway is available and supported."""
        result = {
            "supported": False,
            "reason": "",
            "version": "",
            "supports_led_commands": False,
        }
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.connect((ip, port))
                s.settimeout(5)
                s.sendall(AuthenticateCommand().serialize())
                data = s.recv(1024)
                parsed_response = parse_response(data)
                if (
                    parsed_response.get("type") != "acknowledgment"
                    and parsed_response.get("subtype", False)
                    != "keep_alive_acknowledgment"
                ):
                    result["reason"] = "auth_failed"
                else:
                    s.sendall(GetControllerVersionCommand().serialize())
                    for _ in range(3):
                        data = s.recv(1024)
                        parsed_response = parse_response(data)
                        if parsed_response.get("type", None) != "version":
                            continue
                        result["version"] = (
                            str(parsed_response.get("major_version", 0))
                            + "."
                            + str(parsed_response.get("minor_version", 0))
                        )
                        if parsed_response.get(
                            "minor_version", 0
                        ) < SUPPORTED_VERSIONS.get(
                            parsed_response.get("major_version", 0), 200
                        ):
                            result["reason"] = "unsupported_version"
                        else:
                            result["supported"] = True
                        break
                    s.close()
                    result["supports_led_commands"] = (
                        parsed_response.get("major_version", 0) >= 9
                        or parsed_response.get("major_version", 0) < 1
                    )
                    _LOGGER.debug(result)
                    return result
            except (ConnectionError, TimeoutError):
                result["reason"] = "connection_error"
                s.close()
        return result

    async def close(self):
        """Close the controller."""
        self.enabled = False
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
        self.response_queue.append(response)
        return True

    async def response_thread_loop(self):
        """Loop to handle incoming responses from the controller in a threaded manner."""
        response_tasks = set[Any]()
        while self.enabled:
            pending = list[bytes](self.response_queue)
            self.response_queue.clear()
            for response in pending:
                task = asyncio.create_task(self._response_task(response))

                def _log_done(t: asyncio.Task) -> None:
                    try:
                        result = t.result()
                        _LOGGER.debug(
                            "Response handler finished successfully: %s", result
                        )
                    except Exception as err:  # noqa: BLE001
                        _LOGGER.warning("Response handler finished with error: %s", err)

                task.add_done_callback(_log_done)
                response_tasks.add(task)
            # Remove done tasks
            done = {t for t in response_tasks if t.done()}
            response_tasks.difference_update(done)
            await asyncio.sleep(0.01)

    async def _response_task(self, response):
        """Handle incoming response from the controller."""
        if not await self._validate_single_response(response):
            return await self._handle_multiple_messages(response)
        try:
            _LOGGER.debug(("Received Response: ", response))
            self.last_incoming_message = datetime.datetime.now()
            response_hex = response.hex()
            _LOGGER.debug(
                "Response hex starts with: %s (checking for 5654483c)",
                response_hex[:20],
            )
            if response_hex.startswith("5654483c"):  # Params Received
                _LOGGER.debug(
                    "Parameter API response detected, vitrea_db_reader exists: %s",
                    self.vitrea_db_reader is not None,
                )
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
                            _LOGGER.debug(
                                "Keep Alive Acknowledged at %s",
                                item.get("timestamp"),
                            )
                    elif "status" in item.get("type", ""):
                        _LOGGER.debug("Received Status Update")
                        await self.publish_updates(item)
                # Status Update Received
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
