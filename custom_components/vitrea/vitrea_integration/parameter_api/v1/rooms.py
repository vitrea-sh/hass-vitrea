from .base import ParameterReader, CommandNumber

class GetRoomNumbers(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetRoomNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.rooms = None

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=1)
        self.command_str += chr(0) # Group Number = 0 - not used feature in the protocol.
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
        self.number_of_rooms = response_dict["raw_data"].pop(0)
        self.rooms_list = await self.response_parser.combine_bytes_to_words(response_dict["raw_data"])
        return self.rooms_list

class GetRoomParams(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetRoomParams

    def __init__(self, room_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.room_id = room_id
        self.floor_id = None
        self.command_data = ""
        self.command_str = ""
        self.floor_data = None

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.room_id)
        await self.add_checksum()
        return self.command_str
    
    async def get_data(self, reader, writer) -> list:
        if not self.command_str:
            await self.generate_command()
        response = await self.fetch_data_from_controller(reader, writer, obj_id=self.room_id)
        await self.parse_response(response)
        if not self.response_parser:
            raise ValueError("No response received")
        response_dict = self.response_parser.response_dict
        room_id = await self._byte_list_to_hex(response_dict["raw_data"][:2])
        floor_id = await self._byte_list_to_hex(response_dict["raw_data"][2:4])
        if not room_id == self.room_id:
            raise ValueError("Room ID mismatch")
        name_len = response_dict["raw_data"][4]
        name_data = response_dict["raw_data"][5:]
        room_name = await self.response_parser.byte_list_to_string(name_data)
        if not name_len / 2 == len(room_name):
            raise ValueError("Floor name length mismatch")
        return {"id": room_id, "name": room_name, 'floor_id': floor_id, "keys": {}, "acs": {}}