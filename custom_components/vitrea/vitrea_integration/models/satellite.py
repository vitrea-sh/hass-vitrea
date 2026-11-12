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
        self._reset_task: asyncio.Task | None = None
        self._event_callbacks = set()

    def register_event_callback(self, callback) -> None:
        """Register a callback fired once per raw button event.

        Unlike the state callbacks, these fire for EVERY press — including
        repeated Short presses within the 1s state-reset window that a
        state-based consumer cannot distinguish.
        """
        self._event_callbacks.add(callback)

    def remove_event_callback(self, callback) -> None:
        """Remove a previously registered event callback."""
        self._event_callbacks.discard(callback)

    async def get_state(self):
        pass

    async def update_state(self, data):
        event_data = self._VITREA_TO_HASS_MAPPING.get(data.get("sub_type"))
        if event_data is None:
            return
        for callback in list(self._event_callbacks):
            try:
                callback(event_data)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Event callback failed for %s: %s", self._id, err)
        self.native_value = event_data
        await self.publish_updates()
        if event_data == "Short":
            # Reset in the background: sleeping here would stall the
            # (sequential) response pipeline for a full second per press.
            if self._reset_task and not self._reset_task.done():
                self._reset_task.cancel()
            self._reset_task = asyncio.create_task(self._reset_after_short())

    async def _reset_after_short(self):
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