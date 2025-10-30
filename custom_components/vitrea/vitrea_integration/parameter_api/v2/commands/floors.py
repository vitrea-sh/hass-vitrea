from ....utils.enums import CommandNumber
from .base import BaseParameterCommandGenerator

class GetFloorNumbers(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetFloorNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.floors = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length()
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")
    
class GetFloorParams(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetFloorParams

    def __init__(self, floor_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.floor_id = floor_id
        self.command_data = ""
        self.command_str = ""
        self.floor_data = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.floor_id)
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")