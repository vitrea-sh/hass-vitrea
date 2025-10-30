from ....utils.enums import CommandNumber
from .base import BaseParameterCommandGenerator

class GetACNumbers(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetACNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.acs = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length()
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")
    
class GetACParams(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetACParams

    def __init__(self, ac_id: int, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.ac_id = ac_id
        self.room_id = None
        self.command_data = ""
        self.command_str = ""

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.ac_id)
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")