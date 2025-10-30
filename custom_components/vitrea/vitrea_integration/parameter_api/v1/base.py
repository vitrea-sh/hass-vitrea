from ...control_api.commands.base import Command
from ...control_api.responses.parsers.base import ResponseParser
import struct
from enum import Enum
import asyncio


class CommandNumber(Enum):
    GetFloorNumbers = 1
    GetFloorParams = 2
    GetRoomNumbers = 3
    GetRoomParams = 4
    GetKeypadNumbers = 5
    GetKeyParams = 6
    GetACNumbers = 7
    GetACParams = 8
    GetSceneNumbers = 9
    GetSceneParams = 10


class ParameterCommand(Command):
    HEADER = "VTH>"

    def __init__(self, command_number: CommandNumber):
        super().__init__()
        self.command_number = command_number
        self.command_start = f"{self.HEADER}{chr(self.command_number.value)}"

    async def get_length(self, data_length: int = 0):
        # This function returns two bytes in binary format Hi-Lo - as string(2 hex digits)
        if not hasattr(self, "command_data"):
            raise ValueError(
                "get_length must be called after setting command_data attribute"
            )
        post_command_length = (
            len(self.command_data) + data_length + 1
        )  # 1 byte for checksum
        return "".join(
            chr(int(ch)) for ch in str(struct.pack(">B", post_command_length).hex())
        )

    async def add_checksum(self) -> int:
        if not hasattr(self, "command_str"):
            raise ValueError(
                "add_checksum must be called after setting command attribute"
            )
        checksum = sum(ord(c) for c in self.command_str) % 256
        self.command_str += chr(checksum)
        return checksum

    @staticmethod
    async def _byte_list_to_hex(byte_list):
        return int.from_bytes(byte_list, byteorder="big")


class ParameterResponseParser(ResponseParser):
    RESPONSE_HEADER = "VTH<"

    def __init__(self, response: int, command_number: CommandNumber):
        self.command_number = command_number
        self.response = response
        self.response_bytes = None
        self.response_dict = None

    async def async_init(self):
        self.response_bytes = await self._hex_to_byte_list(self.response)
        await self.validate()
        self.response_dict = await self.parse()

    @staticmethod
    async def _hex_to_byte_list(hex_int):
        # Convert the hex integer to a binary string, removing the '0b' prefix
        binary_str = bin(hex_int)[2:]

        # Pad the binary string to make its length a multiple of 8
        padded_binary = binary_str.zfill(len(binary_str) + 8 - len(binary_str) % 8)

        # Split the binary string into chunks of 8 bits
        byte_chunks = [
            padded_binary[i : i + 8] for i in range(0, len(padded_binary), 8)
        ]

        # Convert each chunk back to an integer
        byte_list = [int(chunk, 2) for chunk in byte_chunks]

        return byte_list

    async def byte_list_to_string(self, byte_list):
        word_list = await self.combine_bytes_to_words(byte_list)
        result = ""
        for word in word_list:
            packed_word = struct.pack("<H", word)
            decoded_char = packed_word.decode("utf-16be")
            result += decoded_char
        return result

    @staticmethod
    async def validate_checksum(response_bytes: list):
        return sum(response_bytes[0:-1]) % 256 == response_bytes[-1]

    @staticmethod
    async def combine_bytes_to_words(byte_list):
        word_list = []
        for i in range(0, len(byte_list), 2):
            # Combine each pair of bytes into a word (16-bit integer)
            word = (byte_list[i] << 8) + byte_list[i + 1]
            word_list.append(word)
        return word_list

    async def validate(self):
        if not await self.validate_checksum(self.response_bytes):
            raise ValueError("Invalid checksum")
        for i, b in enumerate(self.response_bytes[0:4]):
            if b != ord(self.RESPONSE_HEADER[i]):
                raise ValueError("Invalid header")
        if not self.response_bytes[4] == self.command_number.value:
            raise ValueError("Wrong Command")
        self.data_length = struct.unpack(">H", bytes(self.response_bytes[5:7]))[0]
        if not self.data_length == len(self.response_bytes[7:]):
            raise ValueError("Invalid data length")

    async def parse(self):
        if not self.response_bytes:
            await self.async_init()
        response_length = struct.unpack(">H", bytes(self.response_bytes[5:7]))[0]
        data = self.response_bytes[7:-1]

        return {
            "raw_data": data,
            "data_length": response_length - 1,
        }


class ParameterReader(ParameterCommand):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.response_parser = None

    async def serialize(self):
        self.command_hex = self.command_str.encode().hex()
        return self.command_hex

    async def parse_response(self, response: int):
        self.response_parser = ParameterResponseParser(response, self.command_number)
        await self.response_parser.parse()
        return self.response_parser.response_dict

    async def fetch_data_from_controller(self, read, write, obj_id=None):
        # give 1 second to get a response
        result = None
        for i in range(5):
            try:
                result = await asyncio.wait_for(
                    self._fetch_data(read, write, obj_id), timeout=1
                )
                if result:
                    return result
            except asyncio.TimeoutError:
                continue
        raise TimeoutError("No response received")

    async def _fetch_data(self, read, write, obj_id):
        await write(self.command_str.encode())
        result = False
        while not result:
            result = await read(self.command_number, obj_id)
            await asyncio.sleep(0.01)
        return result

    @staticmethod
    async def _int_to_hex_word(int_num: int) -> str:
        result = ""
        int_with_zeros = format(int_num, "04x")
        for i in range(0, len(int_with_zeros), 2):
            int_number = int(int_with_zeros[i : i + 2], 16)
            result += chr(int_number)
        return result
