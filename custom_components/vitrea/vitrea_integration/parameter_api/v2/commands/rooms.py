from ....utils.enums import CommandNumber
from .base import BaseParameterCommandGenerator

class GetRoomNumbers(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetRoomNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.rooms = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=1)
        self.command_str += chr(0) # Group Number = 0 - not used feature in the protocol.
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")
    
class GetRoomParams(BaseParameterCommandGenerator):
    COMMAND_NUMBER = CommandNumber.GetRoomParams

    def __init__(self, room_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.room_id = room_id
        self.command_data = ""
        self.command_str = ""
        self.room_data = None

    async def serialize(self) -> bytes:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.room_id)
        await self.add_checksum()
        return self.command_str.encode(encoding="raw_unicode_escape")