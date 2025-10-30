from ....utils.enums import CommandNumber
from .base import BaseParameterResponseParser
from ..commands.scenarios import GetScenarioParams
from ....models.database import ScenarioModel

class ScenarioNumbersParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetSceneNumbers
    SHOULD_WRITE = True
    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.number_of_scenarios = None
        self.scenarios_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        self.number_of_scenarios = processed_data.pop(0)
        self.scenarios_list = await self.combine_bytes_to_words(processed_data)
        self.validate_data(self.number_of_scenarios, self.scenarios_list)
        # Store remaining scenarios for sequential processing (excluding first, which we queue now)
        if len(self.scenarios_list) > 1:
            self.send_callback.store_pending_scenarios(self.scenarios_list[1:])
        # Queue only the first scenario params request
        if self.scenarios_list:
            from ..commands.scenarios import GetScenarioParams
            await self.send_callback(GetScenarioParams(self.scenarios_list[0]))
        return {"no_of_scenarios": self.number_of_scenarios}
    
    def validate_data(self, number_of_scenarios, scenarios_list):
        if not number_of_scenarios == len(scenarios_list):
            raise ValueError("Number of scenarios does not match the number of scenarios in the list")

class ScenarioParamsParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetSceneParams
    SHOULD_WRITE = False

    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.scenario_id = None
        self.room_id = None
        self.scenario_data = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        scenario_id = await self._byte_list_to_hex(processed_data[:2])
        room_id = await self._byte_list_to_hex(processed_data[2:4])
        name_len = processed_data[4]
        name_data = processed_data[5:]
        scenario_name = await self.byte_list_to_string(name_data)
        self.validate_data(scenario_name, name_len)
        result = [ScenarioModel(id=scenario_id, name=scenario_name, room_id=room_id)]
        # Queue next scenario params request if any pending
        await self.send_callback.queue_next_scenario()
        return result
    
    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")
        