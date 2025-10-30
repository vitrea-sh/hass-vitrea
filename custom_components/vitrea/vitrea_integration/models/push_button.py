from .base import BaseDevice
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes
import logging
from ..control_api.commands import (
    LedIndicatorOnCommand,
    LedIndicatorOffCommand,
    GetKeyStatusCommand,
)

_LOGGER = logging.getLogger(__name__)


class PushButton(BaseDevice):
    supported_key_types = [KeyTypes.PushButton.value]

    def __init__(
        self,
        node_id,
        key_id,
        key_name,
        room_name,
        controller,
        initial_state: bool = False,
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
        self._state = initial_state
        self.indicator_value = False

    @property
    def state(self) -> bool:
        """Return the state of the push button."""
        return self._state

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return self._state

    @is_on.setter
    def is_on(self, value: bool):
        """Set the state of the push button."""
        self._state = value

    async def update_state(self, data):
        """Update the state of the push button."""
        self.is_on = data.get("status")
        await self.publish_updates()

    async def turn_on_indicator(self):
        """Turn on the indicator of the push button."""
        await self.controller.connection.send(
            LedIndicatorOnCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        self.indicator_value = True
        await self.publish_updates()
        return True

    async def turn_off_indicator(self):
        """Turn off the indicator of the push button."""
        await self.controller.connection.send(
            LedIndicatorOffCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        self.indicator_value = False
        await self.publish_updates()
        return True

    async def get_state(self):
        """Get the state of the push button."""
        return await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
