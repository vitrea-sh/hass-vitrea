from .acs import GetACNumbers, GetACParams
from .base import CommandNumber
from .floors import GetFloorNumbers, GetFloorParams
from .keys import GetKeypadNumbers, GetKeyParams
from .rooms import GetRoomNumbers, GetRoomParams
from .scenarios import GetScenarioNumbers, GetScenarioParams
import logging

_LOGGER = logging.getLogger(__name__)


class VitreaDatabaseReader:
    RESPONSE_CALLBACK_MAP = {
        CommandNumber.GetFloorNumbers: None,
        CommandNumber.GetFloorParams: {},
        CommandNumber.GetRoomNumbers: None,
        CommandNumber.GetRoomParams: {},
        CommandNumber.GetKeypadNumbers: None,
        CommandNumber.GetKeyParams: {},
        CommandNumber.GetACNumbers: None,
        CommandNumber.GetACParams: {},
        CommandNumber.GetSceneNumbers: None,
        CommandNumber.GetSceneParams: {},
    }

    def __init__(self, write):
        self.writer = write
        self.reader = self.check_for_response
        self.data = None
        self.floors = {}
        self.rooms = {}
        self.keypads = {}
        self.acs = {}
        self.scenarios = {}
        self.response_callbacks = self.RESPONSE_CALLBACK_MAP

    async def check_for_response(self, command_type: str, obj_id: int = None):
        if command_type in self.response_callbacks:
            if isinstance(self.response_callbacks[command_type], dict):
                if not obj_id:
                    raise ValueError("obj_id is required for this command")
                return self.response_callbacks[command_type].get(obj_id, False)
            else:
                return self.response_callbacks.pop(command_type, None)
        return False

    async def get_floors(self):
        floor_ids = await GetFloorNumbers().get_data(
            reader=self.reader, writer=self.writer
        )
        all_floors = [
            await GetFloorParams(floor_id=floor_id).get_data(
                reader=self.reader, writer=self.writer
            )
            for floor_id in floor_ids
        ]
        for floor in all_floors:
            self.floors[floor.get("id")] = floor
        return all_floors

    async def get_rooms(self):
        room_ids = await GetRoomNumbers().get_data(
            reader=self.reader, writer=self.writer
        )
        all_rooms = [
            await GetRoomParams(room_id=room_id).get_data(
                reader=self.reader, writer=self.writer
            )
            for room_id in room_ids
        ]
        for room in all_rooms:
            self.rooms[room.get("id")] = room
        return all_rooms

    async def get_keys(self):
        keypads_info = await GetKeypadNumbers().get_data(
            reader=self.reader, writer=self.writer
        )
        all_keys = []
        for keypad_info in keypads_info:
            keypad_data = await GetKeyParams(
                keypad_id=keypad_info["id"], number_of_keys=keypad_info["no_of_keys"]
            ).get_data(reader=self.reader, writer=self.writer)
            all_keys.extend(keypad_data)
            self.keypads[f"N{format(keypad_info['id'], '03')}"] = {
                "keys": keypad_data,
                **keypad_info,
            }
        return all_keys

    async def get_acs(self):
        ac_ids = await GetACNumbers().get_data(reader=self.reader, writer=self.writer)
        all_acs = []
        for ac_id in ac_ids:
            ac_params = await GetACParams(ac_id=ac_id).get_data(
                reader=self.reader, writer=self.writer
            )
            all_acs.append(ac_params)
            self.acs[f"A{format(ac_id, '03')}"] = ac_params
        return all_acs

    async def get_scenarios(self):
        scenario_ids = await GetScenarioNumbers().get_data(
            reader=self.reader, writer=self.writer
        )
        all_scenarios = []
        for scenario_id in scenario_ids:
            scenario_params = await GetScenarioParams(scenario_id=scenario_id).get_data(
                reader=self.reader, writer=self.writer
            )
            all_scenarios.append(scenario_params)
            self.scenarios[f"S{format(scenario_id, '03')}"] = scenario_params
        return all_scenarios

    async def response_callback(self, response):
        response_identifier = response.hex()[8:10]
        obj_id = int(response.hex()[14:18], 16)
        bytes_response = int.from_bytes(
                    response, byteorder="big"
                )
        match response_identifier:
            case "01":
                self.response_callbacks[CommandNumber.GetFloorNumbers] = int.from_bytes(
                    response, byteorder="big"
                )
            case "02":
                self.response_callbacks[CommandNumber.GetFloorParams][obj_id] = int.from_bytes(
                    response, byteorder="big"
                )
            case "03":
                self.response_callbacks[CommandNumber.GetRoomNumbers] = int.from_bytes(
                    response, byteorder="big"
                )
            case "04":
                self.response_callbacks[CommandNumber.GetRoomParams][obj_id] = int.from_bytes(
                    response, byteorder="big"
                )
            case "05":
                self.response_callbacks[
                    CommandNumber.GetKeypadNumbers
                ] = int.from_bytes(response, byteorder="big")
            case "06":
                self.response_callbacks[CommandNumber.GetKeyParams][obj_id] = int.from_bytes(
                    response, byteorder="big"
                )
            case "07":
                self.response_callbacks[CommandNumber.GetACNumbers] = int.from_bytes(
                    response, byteorder="big"
                )
            case "08":
                self.response_callbacks[CommandNumber.GetACParams][obj_id] = int.from_bytes(
                    response, byteorder="big"
                )
            case "09":
                self.response_callbacks[CommandNumber.GetSceneNumbers] = int.from_bytes(
                    response, byteorder="big"
                )
            case "0a":
                self.response_callbacks[CommandNumber.GetSceneParams][obj_id] = int.from_bytes(
                    response, byteorder="big"
                )
            case _:
                raise ValueError("Invalid response identifier")

    async def read_vitrea_controller(self):
        # Running all the fetchers async
        fetchers = [
            self.get_floors,
            self.get_rooms,
            self.get_keys,
            self.get_acs,
            self.get_scenarios,
        ]
        for fetcher in fetchers:
            await self._safe_read_controller(fetcher)

    async def _safe_read_controller(self, func):
        success = False
        for i in range(5):
            try:
                await func()
                success = True
                break
            except ValueError as e:
                _LOGGER.error(f"Attempt {i}: Error reading Vitrea DB: {e}")
        if not success:
            raise ValueError("Error reading Vitrea DB - Too many attempts")

    async def serialize(self):
        data = {"floors": [], "scenarios": []}
        for floor_id, floor in self.floors.items():
            floor_rooms = [
                room for room in self.rooms.values() if room.get("floor_id") == floor_id
            ]
            floor_data = {**floor, "rooms": []}
            for room in floor_rooms:
                _room = {**room}
                _room["keys"] = []
                for keypad in self.keypads.values():
                    _room["keys"].extend(
                        [
                            key
                            for key in keypad.get("keys")
                            if key.get("room_id") == room.get("id")
                        ]
                    )
                _room["acs"] = [
                    ac
                    for ac in self.acs.values()
                    if ac.get("room_id") == room.get("id")
                ]
                _room["scenarios"] = [
                    scenario
                    for scenario in self.scenarios.values()
                    if scenario.get("room_id") == room.get("id")
                ]
                floor_data["rooms"].append(_room)
            data["floors"].append(floor_data)
        data["scenarios"] = [
            scenario
            for scenario in self.scenarios.values()
            if scenario.get("room_id") == 65535
        ]
        return data
