from ....utils.enums import CommandNumber
from .base import BaseParameterCommandGenerator

class GetKeypadNumbers(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetKeypadNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.keypads = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length()
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")
    
class GetKeyParams(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetKeyParams

    def __init__(self, keypad_id, key_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.keypad_id = keypad_id
        self.key_id = key_id
        self.command_data = ""
        self.command_str = ""

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=3)
        self.command_str += await self._int_to_hex_word(self.keypad_id)
        self.command_str += chr(self.key_id)
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")