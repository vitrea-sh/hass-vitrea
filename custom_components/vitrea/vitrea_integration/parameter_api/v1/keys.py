from .base import ParameterReader, CommandNumber

class GetKeypadNumbers(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetKeypadNumbers

    def __init__(self, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.command_data = ""
        self.command_str = ""
        self.keypads = None

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
        self.number_of_keypads = response_dict["raw_data"][:2]
        # keypads_data = 
        #self.keypads_list = await self.response_parser.combine_bytes_to_words(response_dict["raw_data"][2:])
        self.keypads_list = await self.parse_keypads_info(response_dict["raw_data"][2:])
        return self.keypads_list
        
    async def parse_keypads_info(self, vbox_data:list):
        # split the list into sublists of 3 elements each
        keypads_info = [vbox_data[x:x+3] for x in range(0, len(vbox_data), 3)]
        keypads = []
        for keypad in keypads_info:
            keypad_id = await self.response_parser.combine_bytes_to_words(keypad[0:2])
            keypad_id = keypad_id[0]
            keypad_no_of_keys = keypad[2]
            keypads.append({"id": keypad_id, "no_of_keys": keypad_no_of_keys})
        return keypads
    
class GetKeyParams(ParameterReader):
    COMMAND_NUMBER = CommandNumber.GetKeyParams

    def __init__(self, keypad_id, number_of_keys, *args, **kwargs):
        super().__init__(command_number=self.COMMAND_NUMBER, *args)
        self.keypad_id = keypad_id
        self.number_of_keys = number_of_keys
        self.room_id = None
        self.command_data = ""
        self.command_str = ""

    async def generate_command(self, key_id) -> str:
        self.command_str = self.command_start
        self.command_str += await self.get_length(data_length=3)
        self.command_str += await self._int_to_hex_word(self.keypad_id)
        self.command_str += chr(key_id)
        await self.add_checksum()
        return self.command_str
    
    async def get_data(self, reader, writer) -> list:
        keys_list = []
        for key_id in range(1, self.number_of_keys+1):
            await self.generate_command(key_id)
            response = await self.fetch_data_from_controller(reader, writer, obj_id=self.keypad_id)
            await self.parse_response(response)
            if not self.response_parser:
                raise ValueError("No response received")
            # Data Division: Keypad ID(2 bytes), Key ID(1 Byte), Key Type(1 Byte), Room Number(2 Bytes), Key Name Length(1 Byte), Key Name(Variable)
            key_params = {}
            key_params["keypad_id"] = await self._byte_list_to_hex(self.response_parser.response_dict["raw_data"][:2])
            key_params["key_id"] = self.response_parser.response_dict["raw_data"][2]
            key_params["key_type"] = self.response_parser.response_dict["raw_data"][3]
            key_params["room_id"] = await self._byte_list_to_hex(self.response_parser.response_dict["raw_data"][4:6])
            key_name_len = self.response_parser.response_dict["raw_data"][6]
            key_name_data = self.response_parser.response_dict["raw_data"][7:]
            key_name = await self.response_parser.byte_list_to_string(key_name_data)
            if not key_name_len / 2 == len(key_name):
                raise ValueError("Key name length mismatch")
            key_params["name"] = key_name
            keys_list.append(key_params)
        return keys_list
    