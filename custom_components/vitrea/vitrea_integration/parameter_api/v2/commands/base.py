import struct
from ....utils.enums import CommandNumber


class BaseParameterCommandGenerator:
    HEADER = "VTH>"

    def __init__(self, command_number: CommandNumber):
        self.command_number = command_number
        self.command_start = f"{self.HEADER}{chr(self.command_number.value)}"

    async def get_length(self, data_length: int = 0):
        if not hasattr(self, "command_data"):
            raise ValueError(
                "get_length must be called after setting command_data attribute"
            )
        post_command_length = len(self.command_data) + data_length + 1
        return "".join(
            chr(int(ch)) for ch in str(struct.pack(">B", post_command_length).hex())
        )

    async def add_checksum(self) -> int:
        if not hasattr(self, "command_str"):
            raise ValueError(
                "add_checksum must be called after setting command attribute"
            )
        checksum = sum(ord(c) for c in self.command_str) % 256
        self.command_str += chr(checksum & 0xFF)
        return checksum

    @staticmethod
    async def _byte_list_to_hex(byte_list):
        return int.from_bytes(byte_list, byteorder="big")
    
    @staticmethod
    async def _int_to_hex_word(int_num: int) -> str:
        result = ""
        int_with_zeros = format(int_num, "04x")
        for i in range(0, len(int_with_zeros), 2):
            int_number = int(int_with_zeros[i : i + 2], 16)
            result += chr(int_number)
        return result
    
    async def serialize(self):
        """
        Serialize the command into the format that the VBox expects.
        This method must be implemented by all subclasses.

        :return: The serialized command string.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    async def validate(self):
        """
        Validate the command parameters.
        This can be overridden by subclasses if specific validation logic is needed.

        :return: None
        :raises: ValueError if validation fails.
        """
        pass  