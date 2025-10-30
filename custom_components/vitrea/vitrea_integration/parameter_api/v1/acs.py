from .base import ParameterReader, CommandNumber

class GetACNumbers(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetACNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.acs_list = None

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
        self.number_of_acs = response_dict["raw_data"].pop(0)
        self.acs_list = await self.response_parser.combine_bytes_to_words(response_dict["raw_data"])
        if not self.number_of_acs == len(self.acs_list):
            raise ValueError("Number of ACs does not match the number of ACs in the list")
        return self.acs_list
    
class GetACParams(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetACParams

    def __init__(self, ac_id, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.ac_id = ac_id
        self.room_id = None
        self.command_data = ""
        self.command_str = ""

    async def generate_command(self) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=2)
        self.command_str += await self._int_to_hex_word(self.ac_id)
        await self.add_checksum()
        return self.command_str
    
    @staticmethod
    async def ascii_digit_to_int(digit: int) -> int:
        if not 48 <= digit <= 57:
            raise ValueError("Not a digit")
        return digit - 48
    
    async def get_data(self, reader, writer) -> list:
        if not self.command_str:
            await self.generate_command()
        response = await self.fetch_data_from_controller(reader, writer, obj_id=self.ac_id)
        await self.parse_response(response)
        if not self.response_parser:
            raise ValueError("No response received")
        response_dict = self.response_parser.response_dict
        ac_id = await self._byte_list_to_hex(response_dict["raw_data"][:2])
        ac_type = await self.ascii_digit_to_int(response_dict["raw_data"][2])
        room_id = await self._byte_list_to_hex(response_dict["raw_data"][3:5])
        if not ac_id == self.ac_id:
            raise ValueError("AC ID mismatch")
        name_len = response_dict["raw_data"][5]
        name_data = response_dict["raw_data"][6:]
        ac_name = await self.response_parser.byte_list_to_string(name_data)
        if not name_len / 2 == len(ac_name):
            raise ValueError("AC name length mismatch")
        return {"id": ac_id, "name": ac_name, 'room_id': room_id, "ac_type": ac_type}
    