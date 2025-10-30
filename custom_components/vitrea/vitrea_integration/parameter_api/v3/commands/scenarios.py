from ....utils.enums import CommandNumber
from .base import BaseParameterCommandGenerator
from codecs import encode

class GetScenarioNumbers(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetSceneNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.scenarios = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length()
        await self.add_checksum()
        return self.command_str.encode()
    
class GetScenarioParams(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetSceneParams

    def __init__(self, scenario_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.scenario_id = scenario_id
        self.room_id = None
        self.command_data = ""
        self.command_str = ""
        self.scenario_data = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.scenario_id)
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")