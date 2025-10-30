import asyncio
import datetime
import logging
from typing import Callable, Optional

from .commands.acs import GetACNumbers
from .commands.base import BaseParameterCommandGenerator
from .commands.floors import GetFloorNumbers
from .commands.keys import GetKeypadNumbers
from .commands.rooms import GetRoomNumbers
from .commands.scenarios import GetScenarioNumbers
from .responses.parser import DBResponseParserFactory

from ...models.database import (
    AirConditionerModel,
    BaseVitreaModel,
    FloorModel,
    KeyModel,
    KeypadModel,
    RoomModel,
    ScenarioModel,
    VitreaDatabaseModel,
)

_LOGGER = logging.getLogger(__name__)


class SequentialCallback:
    """
    Callback wrapper that provides sequential processing capabilities.
    
    This class wraps the reader and provides methods to:
    - Queue commands for sequential execution
    - Store pending items for each entity type
    - Queue the next item request after processing current response
    """

    def __init__(self, reader):
        self.reader = reader

    async def __call__(self, command_generator: BaseParameterCommandGenerator):
        """Queue a command to be sent after current request completes."""
        await self.reader._queue_command(command_generator)

    def store_pending_floors(self, floors_list: list):
        """Store pending floor IDs to process sequentially."""
        self.reader._pending_floors = floors_list.copy()

    def store_pending_rooms(self, rooms_list: list):
        """Store pending room IDs to process sequentially."""
        self.reader._pending_rooms = rooms_list.copy()

    def store_pending_acs(self, acs_list: list):
        """Store pending AC IDs to process sequentially."""
        self.reader._pending_acs = acs_list.copy()

    def store_pending_scenarios(self, scenarios_list: list):
        """Store pending scenario IDs to process sequentially."""
        self.reader._pending_scenarios = scenarios_list.copy()

    def store_pending_keys(self, keys_dict: dict):
        """Store pending keys structure: {keypad_id: [key_id1, key_id2, ...]}"""
        self.reader._pending_keys = keys_dict.copy()

    async def queue_next_floor(self):
        """Queue next floor params request if any pending."""
        if self.reader._pending_floors:
            floor_id = self.reader._pending_floors.pop(0)
            from .commands.floors import GetFloorParams
            await self.reader._queue_command(GetFloorParams(floor_id))

    async def queue_next_room(self):
        """Queue next room params request if any pending."""
        if self.reader._pending_rooms:
            room_id = self.reader._pending_rooms.pop(0)
            from .commands.rooms import GetRoomParams
            await self.reader._queue_command(GetRoomParams(room_id))

    async def queue_next_ac(self):
        """Queue next AC params request if any pending."""
        if self.reader._pending_acs:
            ac_id = self.reader._pending_acs.pop(0)
            from .commands.acs import GetACParams
            await self.reader._queue_command(GetACParams(ac_id))

    async def queue_next_scenario(self):
        """Queue next scenario params request if any pending."""
        if self.reader._pending_scenarios:
            scenario_id = self.reader._pending_scenarios.pop(0)
            from .commands.scenarios import GetScenarioParams
            await self.reader._queue_command(GetScenarioParams(scenario_id))

    async def queue_next_key(self):
        """Queue next key params request if any pending."""
        if not self.reader._pending_keys:
            return
        
        # Find first keypad with remaining keys
        for keypad_id, key_ids in list(self.reader._pending_keys.items()):
            if key_ids:
                key_id = key_ids.pop(0)
                # Remove keypad entry if no more keys
                if not key_ids:
                    del self.reader._pending_keys[keypad_id]
                
                # Convert keypad_id 0 to 256 (as per v2 behavior)
                request_keypad_id = keypad_id
                if keypad_id == 0:
                    request_keypad_id = 256
                
                from .commands.keys import GetKeyParams
                await self.reader._queue_command(GetKeyParams(keypad_id=request_keypad_id, key_id=key_id))
                return


class VitreaDatabaseReader:
    """
    Read the Vitrea database and store data in a structured way.

    This class requires a write callback to send commands to the Vitrea controller.
    It implements a promise-based sequential request/response system to ensure
    commands are sent only after receiving the previous command's response.

    Attributes:
        writer: Callback function for sending commands
        db: VitreaDatabaseModel instance storing the parsed database
        pending_request: Future object for the current pending request
        request_lock: Lock ensuring sequential command execution
    """

    def __init__(self, write: Callable):
        """Initialize the database reader with a write callback."""
        self.writer = write
        self.db = VitreaDatabaseModel()
        self.pending_request: Optional[asyncio.Future] = None
        self.request_lock = asyncio.Lock()
        self._follow_up_commands = []
        self._follow_up_task: Optional[asyncio.Task] = None
        # Sequential processing state
        self._pending_floors = []
        self._pending_rooms = []
        self._pending_acs = []
        self._pending_scenarios = []
        self._pending_keys = {}  # Dict: {keypad_id: [key_id1, key_id2, ...]}
        self._sequential_callback = SequentialCallback(self)

    async def send_command(
        self, command_generator: BaseParameterCommandGenerator, timeout: float = 5.0
    ):
        """
        Send a command and wait for its response before allowing next command.

        Args:
            command_generator: Command generator instance
            timeout: Timeout in seconds for waiting for response (default: 5.0)

        Returns:
            Parsed response data

        Raises:
            TimeoutError: If response not received within timeout period
        """
        _LOGGER.debug("send_command() called for: %s", command_generator.command_number)
        async with self.request_lock:
            # Wait for any pending request to complete
            if self.pending_request and not self.pending_request.done():
                _LOGGER.debug("Waiting for previous request to complete")
                try:
                    await self.pending_request
                except Exception:
                    pass  # Previous request failed, continue

            # Create new promise for this request
            self.pending_request = asyncio.Future()
            command = await command_generator.serialize()
            _LOGGER.debug("Sending command: %s", command.hex())
            await self.writer(command)

            # Store reference to the Future before releasing lock
            future = self.pending_request

        # Wait for response outside the lock (will be resolved by feed())
        _LOGGER.debug("Waiting for response with timeout: %s", timeout)
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            _LOGGER.debug("Received response result: %s", result)
            # Wait for any follow-up commands to complete before returning
            # This ensures all follow-ups (including nested ones) are done
            if self._follow_up_task and not self._follow_up_task.done():
                _LOGGER.debug("Waiting for follow-up commands to complete")
                try:
                    await self._follow_up_task
                except Exception as e:
                    _LOGGER.error("Error in follow-up task: %s", e)
                    # Follow-up commands failed, but original command succeeded
            return result
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            _LOGGER.error("Timeout or cancellation waiting for response: %s", e)
            # Clear pending request if it timed out or was cancelled
            async with self.request_lock:
                if self.pending_request is future:
                    self.pending_request = None
            if isinstance(e, asyncio.TimeoutError):
                raise TimeoutError(
                    f"Timeout waiting for response to command {command_generator.command_number}"
                ) from e
            raise

    async def get_floors(self):
        """Request floor numbers from the controller."""
        await self.send_command(GetFloorNumbers())

    async def get_rooms(self):
        """Request room numbers from the controller."""
        await self.send_command(GetRoomNumbers())

    async def get_keypads(self):
        """Request keypad numbers from the controller."""
        await self.send_command(GetKeypadNumbers())

    async def get_acs(self):
        """Request AC numbers from the controller."""
        await self.send_command(GetACNumbers())

    async def get_scenarios(self):
        """Request scenario numbers from the controller."""
        await self.send_command(GetScenarioNumbers())

    async def _queue_command(self, command_generator: BaseParameterCommandGenerator):
        """Queue a command to be sent after current request completes."""
        self._follow_up_commands.append(command_generator)

    async def _process_follow_up_commands(self):
        """Process queued follow-up commands sequentially.
        
        Each command is processed and all its nested follow-ups complete
        before moving to the next command, since send_command() waits for
        follow-up tasks to complete.
        """
        while self._follow_up_commands:
            command_generator = self._follow_up_commands.pop(0)
            # Wait for this command and all its nested follow-ups to complete
            await self.send_command(command_generator)

    async def feed(self, data: bytes):
        """
        Process incoming response and resolve pending promise.

        Args:
            data: Raw response bytes from controller
        """
        _LOGGER.debug("feed() called with data: %s", data.hex()[:50])
        # Resolve pending promise if it exists
        future_to_resolve = None
        async with self.request_lock:
            if self.pending_request and not self.pending_request.done():
                future_to_resolve = self.pending_request
                self.pending_request = None  # Clear before resolving to prevent race
                _LOGGER.debug("Found pending request to resolve")
            else:
                _LOGGER.debug("No pending request found (pending_request: %s, done: %s)", 
                             self.pending_request, 
                             self.pending_request.done() if self.pending_request else None)

        if future_to_resolve is None:
            # No pending request, this might be an unsolicited response
            _LOGGER.debug("Received response but no pending request to resolve")
            return

        try:
            parser = DBResponseParserFactory.create_parser(
                raw_data=data, send_callback=self._sequential_callback
            )
            if parser is None:
                _LOGGER.error("Parser is None for data: %s", data.hex())
                if not future_to_resolve.done():
                    future_to_resolve.set_exception(ValueError("No parser found for response"))
                return
            _LOGGER.debug("Created parser: %s", parser.__class__.__name__)
            items = await parser.parse_response()
            _LOGGER.debug("Parser returned items: %s", type(items))

            # Update database
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, BaseVitreaModel):
                        self.db.add_object(item)
            elif isinstance(items, dict):
                for key, value in items.items():
                    match key:
                        case "no_of_floors":
                            self.db.no_of_floors = value
                        case "no_of_rooms":
                            self.db.no_of_rooms = value
                        case "no_of_keys":
                            self.db.no_of_keys = value
                        case "no_of_acs":
                            self.db.no_of_acs = value
                        case "no_of_scenarios":
                            self.db.no_of_scenarios = value
                        case _:
                            pass
            else:
                _LOGGER.warning("Unknown response for DB Reader: %s", items)

            # Resolve promise first so send_command() can continue
            if not future_to_resolve.done():
                _LOGGER.debug("Resolving promise with result")
                future_to_resolve.set_result(items)
            else:
                _LOGGER.warning("Future already done, cannot resolve")

            # Process follow-up commands asynchronously as a task
            # send_command() will wait for this task to complete
            if self._follow_up_commands:
                async def process_follow_ups():
                    try:
                        await self._process_follow_up_commands()
                    except Exception as e:
                        _LOGGER.error("Error processing follow-up commands: %s", e)
                        raise
                    finally:
                        # Clear the task reference when done
                        self._follow_up_task = None
                
                self._follow_up_task = asyncio.create_task(process_follow_ups())
            else:
                # No follow-up commands, clear any existing task
                self._follow_up_task = None

        except Exception as e:
            _LOGGER.error(e, stack_info=True)
            # Reject promise on error
            if not future_to_resolve.done():
                future_to_resolve.set_exception(e)
            raise

    async def read_vitrea_controller(
        self, force: bool = False, timeout_seconds: int = 45
    ) -> VitreaDatabaseModel:
        """
        Sequentially read all database data from the Vitrea controller.

        Commands are sent one at a time, waiting for each response and all
        follow-up commands to complete before proceeding to the next command.

        Args:
            force: Force reload even if database is already loaded
            timeout_seconds: Total timeout for the entire operation

        Returns:
            VitreaDatabaseModel instance with all loaded data

        Raises:
            TimeoutError: If operation doesn't complete within timeout
        """
        if not self.db.is_loaded() or force:
            timeout = datetime.timedelta(seconds=timeout_seconds)
            start_time = datetime.datetime.now()
            
            # Send commands sequentially, waiting for each response and all follow-ups
            _LOGGER.debug("Starting database read - getting floors")
            await self.get_floors()  # Waits for response and all floor follow-ups
            _LOGGER.debug("Floors loaded: %d/%d", len(self.db.floors), self.db.no_of_floors)
            
            await self.get_rooms()  # Waits for response and all room follow-ups
            _LOGGER.debug("Rooms loaded: %d/%d", len(self.db.rooms), self.db.no_of_rooms)
            
            await self.get_keypads()  # Waits for response and all keypad follow-ups
            _LOGGER.debug("Keypads loaded: %d", len(self.db.keypads))
            
            await self.get_acs()  # Waits for response and all AC follow-ups
            _LOGGER.debug("ACs loaded: %d/%d", len(self.db.air_conditioners), self.db.no_of_acs)
            
            await self.get_scenarios()  # Waits for response and all scenario follow-ups
            _LOGGER.debug("Scenarios loaded: %d/%d", len(self.db.scenarios), self.db.no_of_scenarios)

            # Ensure all follow-up tasks have completed
            if self._follow_up_task and not self._follow_up_task.done():
                _LOGGER.debug("Waiting for final follow-up commands to complete")
                try:
                    await asyncio.wait_for(self._follow_up_task, timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Timeout waiting for final follow-up commands")

            # Final check that database is fully loaded
            # Since send_command() waits for follow-ups, this should be immediate
            attempts = 0
            max_attempts = 50  # 5 seconds max (50 * 0.1s)
            while not self.db.is_loaded():
                attempts += 1
                if attempts > max_attempts:
                    _LOGGER.error(
                        "Database loading check failed after %d attempts. "
                        "Floors: %d/%d, Rooms: %d/%d, Keys: %d/%d, ACs: %d/%d, Scenarios: %d/%d",
                        max_attempts,
                        len(self.db.floors), self.db.no_of_floors,
                        len(self.db.rooms), self.db.no_of_rooms,
                        len(self.db.keys), self.db.no_of_keys,
                        len(self.db.air_conditioners), self.db.no_of_acs,
                        len(self.db.scenarios), self.db.no_of_scenarios
                    )
                    raise TimeoutError(
                        "Timeout while reading Vitrea DB, not all data was loaded. "
                        f"Floors: {len(self.db.floors)}/{self.db.no_of_floors}, "
                        f"Rooms: {len(self.db.rooms)}/{self.db.no_of_rooms}, "
                        f"Keys: {len(self.db.keys)}/{self.db.no_of_keys}, "
                        f"ACs: {len(self.db.air_conditioners)}/{self.db.no_of_acs}, "
                        f"Scenarios: {len(self.db.scenarios)}/{self.db.no_of_scenarios}"
                    )
                if (datetime.datetime.now() - start_time) > timeout:
                    raise TimeoutError(
                        "Timeout while reading Vitrea DB, not all data was loaded"
                    )
                await asyncio.sleep(0.1)
            
            _LOGGER.debug("Database fully loaded")
        return self.db
