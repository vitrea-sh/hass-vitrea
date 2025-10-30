from ....utils.enums import CommandNumber
from .base import BaseParameterResponseParser
from ..commands.floors import GetFloorParams
from ....models.database import FloorModel

class FloorNumbersParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetFloorNumbers
    SHOULD_WRITE = True
    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.number_of_floors = None
        self.floors_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        self.number_of_floors = processed_data.pop(0)
        self.floors_list = await self.combine_bytes_to_words(self.response_hex)
        self.validate_data(self.number_of_floors, self.floors_list)
        for floor in self.floors_list:
            await self.send_callback(GetFloorParams(floor))
        return {"no_of_floors": self.number_of_floors}
    
    def validate_data(self, number_of_floors, floors_list):
        if not number_of_floors == len(floors_list):
            raise ValueError("Number of floors does not match the number of floors in the list")

class FloorParamsParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetFloorParams
    SHOULD_WRITE = False

    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.floor_id = None
        self.floor_name = None
        self.floor_data = None

    async def parse_response(self):
        raw_data = await self.parse_raw()
        self.floor_id = await self._byte_list_to_hex(raw_data[:2])
        name_len = raw_data[2]
        name_data = raw_data[3:]
        self.floor_name = await self.byte_list_to_string(name_data)
        self.validate_data(self.floor_name, name_len)
        return [FloorModel(id=self.floor_id, name=self.floor_name)]
    
    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")