import asyncio
from .base import BaseDevice
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes
import logging
from ..control_api.commands import LedIndicatorOnCommand, LedIndicatorOffCommand
_LOGGER = logging.getLogger(__name__)


class Satellite(BaseDevice):
    supported_key_types = [KeyTypes.Satellite.value]
    _VITREA_TO_HASS_MAPPING = {
        "satellite_key_short": "Short",
        "satellite_key_long": "Long",
        "satellite_key_release": "Release",
    }

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        initial_state: bool = None,
        **kwargs,
    ):
        super().__init__(
            node_id=node_id,
            key_name=key_name,
            room_name=room_name,
            controller=controller,
            **kwargs,
        )
        self.key_id = key_id
        self.native_value = "Release"
        self.indicator_value = False

    async def get_state(self):
        pass

    async def update_state(self, data):
        event_data = self._VITREA_TO_HASS_MAPPING.get(data["sub_type"])
        if event_data is None:
            return
        self.native_value = event_data
        await self.publish_updates()
        if event_data == "Short":
            await asyncio.sleep(1)
            self.native_value = "Release"
            await self.publish_updates()

    async def turn_on_indicator(self):
        await self.controller.connection.send(
            LedIndicatorOnCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        self.indicator_value = True
        await self.publish_updates()
        return True

    async def turn_off_indicator(self):
        await self.controller.connection.send(
            LedIndicatorOffCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        self.indicator_value = False
        await self.publish_updates()
        return True