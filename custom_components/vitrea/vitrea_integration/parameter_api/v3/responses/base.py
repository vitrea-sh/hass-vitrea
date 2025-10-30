from abc import abstractmethod
import struct
from typing import Callable
from ....utils.enums import CommandNumber
from ....models.database import BaseVitreaModel

class BaseParameterResponseParser:
    RESPONSE_HEADER = "VTH<"

    def __init__(self, response: int, command_number: CommandNumber, send_callback:Callable):
        self.command_number = command_number
        self.response = response
        self.response_bytes = None
        self.response_dict = None
        self.send_callback = send_callback

    @abstractmethod
    async def parse_response(self) -> list[BaseVitreaModel]:
        raise NotImplementedError
    
    @property
    def SHOULD_WRITE(self):
        raise NotImplementedError
    
    @property
    def COMMAND_NUMBER(self):
        raise NotImplementedError

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
    
    @staticmethod
    async def _byte_list_to_hex(byte_list):
        return int.from_bytes(byte_list, byteorder="big")

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

    async def parse_raw(self):
        if not self.response_dict:
            self.response_bytes = await self._hex_to_byte_list(self.response)
            self.data_length = struct.unpack(">H", bytes(self.response_bytes[5:7]))[0]
            await self.validate()
            
            response_length = struct.unpack(">H", bytes(self.response_bytes[5:7]))[0]
            data = self.response_bytes[7:-1]
            self.response_hex = data
        return self.response_hex