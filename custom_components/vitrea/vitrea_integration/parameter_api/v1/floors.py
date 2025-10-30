from .base import ParameterReader, CommandNumber

class GetFloorNumbers(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetFloorNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.floors = None

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
        self.number_of_floors = response_dict["raw_data"].pop(0)
        self.floors_list = await self.response_parser.combine_bytes_to_words(response_dict["raw_data"])
        return self.floors_list
        
class GetFloorParams(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetFloorParams

    def __init__(self, floor_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.floor_id = floor_id
        self.command_data = ""
        self.command_str = ""
        self.floor_data = None

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.floor_id)
        await self.add_checksum()
        return self.command_str
    
    async def get_data(self, reader, writer) -> list:
        if not self.command_str:
            await self.generate_command()
        response = await self.fetch_data_from_controller(reader, writer, obj_id=self.floor_id)
        await self.parse_response(response)
        if not self.response_parser:
            raise ValueError("No response received")
        response_dict = self.response_parser.response_dict
        floor_id = await self._byte_list_to_hex(response_dict["raw_data"][:2])
        if not floor_id == self.floor_id:
            raise ValueError("Floor ID mismatch")
        name_len = response_dict["raw_data"][2]
        name_data = response_dict["raw_data"][3:]
        floor_name = await self.response_parser.byte_list_to_string(name_data)
        if not name_len / 2 == len(floor_name):
            raise ValueError("Floor name length mismatch")
        return {"id": floor_id, "name": floor_name, "rooms": []}