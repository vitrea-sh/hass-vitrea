from ....utils.enums import CommandNumber, AirConditionerType
from .base import BaseParameterResponseParser
from ..commands.acs import GetACParams
from ....models.database import AirConditionerModel

class ACNumbersParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetACNumbers
    SHOULD_WRITE = True
    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.number_of_acs = None
        self.acs_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        self.number_of_acs = processed_data.pop(0)
        self.acs_list = await self.combine_bytes_to_words(processed_data)
        self.validate_data(self.number_of_acs, self.acs_list)
        # Store remaining ACs for sequential processing (excluding first, which we queue now)
        if len(self.acs_list) > 1:
            self.send_callback.store_pending_acs(self.acs_list[1:])
        # Queue only the first AC params request
        if self.acs_list:
            from ..commands.acs import GetACParams
            await self.send_callback(GetACParams(self.acs_list[0]))
        return {"no_of_acs": self.number_of_acs}
    
    def validate_data(self, number_of_acs, acs_list):
        if not number_of_acs == len(acs_list):
            raise ValueError("Number of acs does not match the number of acs in the list")
    
class ACParamsParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetACParams
    SHOULD_WRITE = False

    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.ac_id = None
        self.ac_name = None
        self.ac_data = None

    async def parse_response(self):
        proccessed_data = await self.parse_raw()
        ac_id = await self._byte_list_to_hex(proccessed_data[:2])
        ac_type = AirConditionerType(await self._ascii_digit_to_int(proccessed_data[2]))
        room_id = await self._byte_list_to_hex(proccessed_data[3:5])
        name_len = proccessed_data[5]
        name_data = proccessed_data[6:]
        ac_name = await self.byte_list_to_string(name_data)
        self.validate_data(ac_name, name_len)
        result = [AirConditionerModel(id=ac_id, name=ac_name, type=ac_type, room_id=room_id)]
        # Queue next AC params request if any pending
        await self.send_callback.queue_next_ac()
        return result
    
    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")
        
    @staticmethod
    async def _ascii_digit_to_int(digit: int) -> int:
        if not 48 <= digit <= 57:
            raise ValueError("Not a digit")
        return digit - 48

