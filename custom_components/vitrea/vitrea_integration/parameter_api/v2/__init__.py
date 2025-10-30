import asyncio
from typing import Callable
from .commands.floors import GetFloorNumbers
from .commands.rooms import GetRoomNumbers
from .commands.keys import GetKeyParams, GetKeypadNumbers
from .commands.acs import GetACNumbers
from .commands.scenarios import GetScenarioNumbers
from .commands.base import BaseParameterCommandGenerator
from .responses.parser import DBResponseParserFactory
import logging
from ...models.database import (
    VitreaDatabaseModel,
    FloorModel,
    RoomModel,
    KeypadModel,
    KeyModel,
    AirConditionerModel,
    ScenarioModel,
    BaseVitreaModel,
)
import datetime

_LOGGER = logging.getLogger(__name__)


class VitreaDatabaseReader:
    """
    This class is responsible for reading the Vitrea database and storing the data in a structured way.
    It needs to receive a write callback that will be used to send commands to the Vitrea controller.
    It provides the following methods:
    - feed: Feed incoming messages to the reader.
    - read_vitrea_controller: Reads the Vitrea controller database
    - serialize: Serializes the data in a structured way
    """

    def __init__(self, write: Callable):
        self.writer = write
        self.data = None
        self.db = VitreaDatabaseModel()
        self.last_command_sent_timestamp = None
        self.expected_keypads = set()
        self.keypads_to_load = None

    async def send_command(self, command_generator: BaseParameterCommandGenerator):
        command = await command_generator.serialize()
        await self.writer(command)
        self.last_command_sent_timestamp = datetime.datetime.now()

    async def get_floors(self):
        await self.send_command(GetFloorNumbers())

    async def get_rooms(self):
        await self.send_command(GetRoomNumbers())

    async def get_keypads(self):
        await self.send_command(GetKeypadNumbers())

    async def get_acs(self):
        await self.send_command(GetACNumbers())

    async def get_scenarios(self):
        await self.send_command(GetScenarioNumbers())

    async def feed(self, data: bytes):
        try:
            parser = DBResponseParserFactory.create_parser(
                raw_data=data, send_callback=self.send_command
            )
            items = await parser.parse_response()
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, BaseVitreaModel):
                        self.db.add_object(item)
                    if isinstance(item, KeyModel):
                        if self.keypads_to_load.get(item.keypad_id, None):
                            if item.id in self.keypads_to_load[item.keypad_id]:
                                self.keypads_to_load[item.keypad_id].remove(item.id)
                            if not self.keypads_to_load[item.keypad_id]:
                                del self.keypads_to_load[item.keypad_id]
                        if not self.keypads_to_load:
                            self.keypads_to_load = None
            elif isinstance(items, dict):
                for key, value in items.items():
                    match key:
                        case "no_of_floors":
                            self.db.no_of_floors = value
                        case "no_of_rooms":
                            self.db.no_of_rooms = value
                        case "no_of_keys":
                            self.db.no_of_keys = value
                        case "expected_keypads":
                            self.keypads_to_load = value
                        case "no_of_acs":
                            self.db.no_of_acs = value
                        case "no_of_scenarios":
                            self.db.no_of_scenarios = value
                        case _:
                            pass
            else:
                _LOGGER.warning(f"Unknown response for DB Reader: {items}")
        except Exception as e:
            _LOGGER.error(e, stack_info=True)
            
    async def get_missing_keys(self):
        _LOGGER.warning(f"Getting missing keys: {self.keypads_to_load}")
        for keypad_id, keys in self.keypads_to_load.items():
            if keypad_id == 0:
                keypad_id = 256
            for key_id in keys:
                await self.send_command(GetKeyParams(keypad_id=int(keypad_id), key_id=int(key_id)))

    async def read_vitrea_controller(
        self, force: bool = False, timeout_seconds: int = 45
    ) -> VitreaDatabaseModel:
        if not self.db.is_loaded() or force:
            await self.get_floors()
            await self.get_rooms()
            await self.get_keypads()
            await self.get_acs()
            await self.get_scenarios()
            timeout = datetime.timedelta(seconds=timeout_seconds)
            start_time = datetime.datetime.now()
            while not self.db.is_loaded():
                if not self.last_command_sent_timestamp:
                    await asyncio.sleep(0.2)
                    continue
                if (
                    datetime.datetime.now() - self.last_command_sent_timestamp
                ).seconds > 3:
                    if not self.db.is_floors_loaded():
                        _LOGGER.debug("Retrying to get floors")
                        await self.get_floors()
                    if not self.db.is_rooms_loaded():
                        _LOGGER.debug("Retrying to get rooms")
                        await self.get_rooms()
                    if not self.db.is_keys_loaded():
                        if not self.keypads_to_load:
                            _LOGGER.error(f"Expected no of keys: {self.db.no_of_keys}, loaded no of keys: {len(self.db.keys)}")
                            break
                        _LOGGER.debug("Retrying to get keypads")
                        await self.get_missing_keys()
                    if not self.db.is_acs_loaded():
                        _LOGGER.debug("Retrying to get acs")
                        await self.get_acs()
                    if not self.db.is_scenarios_loaded():
                        _LOGGER.debug("Retrying to get scenarios")
                        await self.get_scenarios()
                if (datetime.datetime.now() - start_time) > timeout:
                    raise TimeoutError(
                        "Timeout while reading Vitrea DB, not all data was loaded"
                    )
                await asyncio.sleep(0.2)
        return self.db

    def find_which_keypads_are_missing(self):
        list_of_expected_ids = range(1, 401)
        list_of_loaded_ids = [keypad.id for keypad in self.db.keypads]
        return list(set(list_of_expected_ids) - set(list_of_loaded_ids))
