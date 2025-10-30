from ....utils.enums import CommandNumber
from .base import BaseParameterResponseParser
from ..commands.rooms import GetRoomParams
from ....models.database import RoomModel

class RoomNumbersParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetRoomNumbers
    SHOULD_WRITE = True
    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.number_of_rooms = None
        self.rooms_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        self.number_of_rooms = processed_data.pop(0)
        self.rooms_list = await self.combine_bytes_to_words(self.response_hex)
        self.validate_data(self.number_of_rooms, self.rooms_list)
        # Store remaining rooms for sequential processing (excluding first, which we queue now)
        if len(self.rooms_list) > 1:
            self.send_callback.store_pending_rooms(self.rooms_list[1:])
        # Queue only the first room params request
        if self.rooms_list:
            from ..commands.rooms import GetRoomParams
            await self.send_callback(GetRoomParams(self.rooms_list[0]))
        return {"no_of_rooms": self.number_of_rooms}
    
    def validate_data(self, number_of_floors, floors_list):
        if not number_of_floors == len(floors_list):
            raise ValueError("Number of floors does not match the number of floors in the list")
        
class RoomParamsParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetRoomParams
    SHOULD_WRITE = False

    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.room_id = None
        self.room_name = None
        self.room_data = None

    async def parse_response(self):
        raw_data = await self.parse_raw()
        room_id = await self._byte_list_to_hex(raw_data[:2])
        floor_id = await self._byte_list_to_hex(raw_data[2:4])
        name_len = raw_data[4]
        name_data = raw_data[5:]
        room_name = await self.byte_list_to_string(name_data)
        self.validate_data(room_name, name_len)
        result = [RoomModel(id=room_id, name=room_name, floor_id=floor_id)]
        # Queue next room params request if any pending
        await self.send_callback.queue_next_room()
        return result
       
    
    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")