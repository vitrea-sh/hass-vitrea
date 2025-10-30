from .base import ParameterReader, CommandNumber

class GetScenarioNumbers(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetSceneNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.scenarios_list = None

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length()
        await self.add_checksum()
        return self.command_str
    
    async def get_data(self, reader, writer) -> list:
        if not self.command_str:
            await self.generate_command()
        response = await self.fetch_data_from_controller(reader, writer)
        await self.parse_response(response)
        if not self.response_parser:
            raise ValueError("No response received")
        response_dict = self.response_parser.response_dict
        self.number_of_scenarios = response_dict["raw_data"].pop(0)
        self.scenarios_list = await self.response_parser.combine_bytes_to_words(response_dict["raw_data"])
        if not self.number_of_scenarios == len(self.scenarios_list):
            raise ValueError("Number of scenarios does not match the number of scenarios in the list")
        return self.scenarios_list
    
class GetScenarioParams(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetSceneParams

    def __init__(self, scenario_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.scenario_id = scenario_id
        self.room_id = None
        self.command_data = ""
        self.command_str = ""
        self.scenario_data = None

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.scenario_id)
        await self.add_checksum()
        return self.command_str
    
    async def get_data(self, reader, writer) -> list:
        if not self.command_str:
            await self.generate_command()
        response = await self.fetch_data_from_controller(reader, writer, obj_id=self.scenario_id)
        await self.parse_response(response)
        if not self.response_parser:
            raise ValueError("No response received")
        response_dict = self.response_parser.response_dict
        scenario_id = await self._byte_list_to_hex(response_dict["raw_data"][:2])
        room_id = await self._byte_list_to_hex(response_dict["raw_data"][2:4])
        if not scenario_id == self.scenario_id:
            raise ValueError("Room ID mismatch")
        name_len = response_dict["raw_data"][4]
        name_data = response_dict["raw_data"][5:]
        scenario_name = await self.response_parser.byte_list_to_string(name_data)
        if not name_len / 2 == len(scenario_name):
            raise ValueError("Scenario name length mismatch")
        return {"id": scenario_id, "name": scenario_name, 'room_id': room_id}
