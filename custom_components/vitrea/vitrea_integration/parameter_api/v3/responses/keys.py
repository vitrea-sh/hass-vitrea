from ....utils.enums import CommandNumber
from .base import BaseParameterResponseParser
from ..commands.keys import GetKeyParams
from ....models.database import KeyModel, KeypadModel
from ....utils.enums import KeyTypes

class KeypadNumbersParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetKeypadNumbers
    SHOULD_WRITE = True
    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.number_of_keypads = None
        self.keys_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        
        self.number_of_keypads = await self._byte_list_to_hex(processed_data[:2])

        self.keypads_list = await self._parse_keypads_to_list(processed_data[2:])
        self.validate_data(self.number_of_keypads, self.keypads_list)
        total_no_of_keys = 0
        
        # Build nested structure: {keypad_id: [key_id1, key_id2, ...]}
        pending_keys_dict = {}
        for keypad in self.keypads_list:
            total_no_of_keys += keypad["no_of_keys"]
            keypad_id = keypad["id"]
            # Create list of key IDs for this keypad
            key_ids = list(range(1, keypad["no_of_keys"] + 1))
            if key_ids:
                pending_keys_dict[keypad_id] = key_ids.copy()
        
        # Store pending keys structure for sequential processing
        if pending_keys_dict:
            self.send_callback.store_pending_keys(pending_keys_dict)
            # Queue only the first keypad/key pair
            first_keypad_id = next(iter(pending_keys_dict))
            first_key_id = pending_keys_dict[first_keypad_id][0]
            # Remove first key from pending since we're queuing it now
            pending_keys_dict[first_keypad_id].pop(0)
            if not pending_keys_dict[first_keypad_id]:
                del pending_keys_dict[first_keypad_id]
            # Update stored pending keys
            self.send_callback.store_pending_keys(pending_keys_dict)
            # Queue first key params request
            # Convert keypad_id 0 to 256 (as per v2 behavior)
            request_keypad_id = first_keypad_id
            if first_keypad_id == 0:
                request_keypad_id = 256
            await self.send_callback(GetKeyParams(keypad_id=request_keypad_id, key_id=first_key_id))
        
        return {"no_of_keys": total_no_of_keys}
    
    async def _parse_keypads_to_list(self, keypads_list:list):
        # split the list into sublists of 3 elements each
        keypads_info = [keypads_list[x:x+3] for x in range(0, len(keypads_list), 3)]
        keypads = []
        for keypad in keypads_info:
            keypad_id = await self.combine_bytes_to_words(keypad[0:2])
            keypad_id = keypad_id[0]
            keypad_no_of_keys = keypad[2]
            keypads.append({"id": keypad_id, "no_of_keys": keypad_no_of_keys})
        return keypads

    def validate_data(self, number_of_keypads, keypads_list):
        if not number_of_keypads == len(keypads_list):
            raise ValueError("Number of keys does not match the number of keys in the list")
        
class KeyParamsParser(BaseParameterResponseParser):
    COMMAND_NUMBER = CommandNumber.GetKeyParams
    SHOULD_WRITE = False

    def __init__(self, raw_data:bytes, send_callback):
        int_data = int.from_bytes(raw_data, byteorder='big')
        super().__init__(response=int_data, command_number=self.COMMAND_NUMBER, send_callback=send_callback)
        self.keypad_id = None
        self.keys_list = None

    async def parse_response(self):
        processed_data = await self.parse_raw()
        # Data Division: Keypad ID(2 bytes), Key ID(1 Byte), Key Type(1 Byte), Room Number(2 Bytes), Key Name Length(1 Byte), Key Name(Variable)
        keypad_id = await self._byte_list_to_hex(processed_data[:2])
        key_id = processed_data[2]
        key_type = KeyTypes(processed_data[3])
        room_id = await self._byte_list_to_hex(processed_data[4:6])
        key_name_len = processed_data[6]
        key_name_data = processed_data[7:]
        key_name = await self.byte_list_to_string(key_name_data)
        self.validate_data(key_name, key_name_len)
        result = [KeypadModel(id=keypad_id), KeyModel(keypad_id=keypad_id, id=key_id, type=key_type, name=key_name, room_id=room_id)]
        # Queue next key params request if any pending
        await self.send_callback.queue_next_key()
        return result
        
    def validate_data(self, name, name_len):
        if not name_len / 2 == len(name):
            raise ValueError("Name length mismatch")