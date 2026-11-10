import logging

from ....utils.enums import CommandNumber, AirConditionerType
from .base import BaseParameterResponseParser
from ....models.database import AirConditionerModel

_LOGGER = logging.getLogger(__name__)

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
        ac_type, room_bytes, name_len, name_data = self._detect_layout(
            proccessed_data, ac_id
        )
        room_id = await self._byte_list_to_hex(room_bytes)
        ac_name = await self.byte_list_to_string(name_data)
        self.validate_data(ac_name, name_len)
        result = [AirConditionerModel(id=ac_id, name=ac_name, type=ac_type, room_id=room_id)]
        # Queue next AC params request if any pending
        await self.send_callback.queue_next_ac()
        return result

    @staticmethod
    def _detect_layout(data, ac_id):
        """Resolve the AC parameters layout to (type, room bytes, name_len, name).

        The spec (rev 2.108) promises AC_no(2), thermostat_type(1, one
        ASCII digit '1'-'4'), room_no(2), name_len(1), name — but firmware
        9.50 was observed in the field omitting the thermostat_type byte
        entirely (AC_no, room_no, name_len, name). A binary 1-4 type byte
        is accepted too, since the neighboring count fields already
        deviate from ASCII to binary.
        """
        n = len(data)
        type_byte = data[2] if n > 2 else None
        if n >= 6 and 0x31 <= type_byte <= 0x34:
            # Spec layout: ASCII '1'-'4'.
            return (
                AirConditionerType(type_byte - 0x30), data[3:5], data[5], data[6:]
            )
        if n >= 6 and 1 <= type_byte <= 4 and data[5] == n - 6:
            # Spec layout with a binary type byte.
            return AirConditionerType(type_byte), data[3:5], data[5], data[6:]
        if n >= 5 and data[4] == n - 5:
            # Firmware 9.50: no thermostat_type field at all. Assume Type 1
            # (product decision) so the AC still gets its climate entity.
            _LOGGER.warning(
                "AC %d reports no thermostat type (firmware omitted the "
                "field); assuming Type 1",
                ac_id,
            )
            return AirConditionerType.TYPE_1, data[2:4], data[4], data[5:]
        raise ValueError(
            f"Unrecognized AC parameters layout: {bytes(data).hex()}"
        )

    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")
