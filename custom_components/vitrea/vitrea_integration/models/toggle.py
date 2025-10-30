import asyncio
from ..control_api.commands import (
    ToggleOnCommand,
    ToggleOffCommand,
    ToggleToggleCommand,
    GetKeyStatusCommand,
)
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes

from .base import BaseDevice
# Validate Duration, supported key types and state


class Toggle(BaseDevice):
    supported_key_types = [
        KeyTypes.Toggle.value,
        KeyTypes.Boiler.value,
        KeyTypes.Heater.value,
    ]

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
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
        self._countdown_minutes = 0

    @property
    def state(self) -> bool:
        return self._state

    async def turn_on(self, duration: int = 0) -> bool:
        if not 0 <= duration <= 120:
            raise ValueError("Duration must be between 0 and 120")
        await self.controller.connection.send(
            ToggleOnCommand(
                node_id=self.node_id, key_id=self.key_id, duration=duration
            ).serialize()
        )
        return True

    async def turn_off(self) -> bool:
        await self.controller.connection.send(
            ToggleOffCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def toggle(self) -> bool:
        await self.controller.connection.send(
            ToggleToggleCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def get_state(self):
        return await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return self._state

    @is_on.setter
    def is_on(self, value: bool):
        self._state = value

    @property
    def countdown_minutes(self) -> int:
        """Return the countdown minutes of the switch."""
        return self._countdown_minutes

    async def update_state(self, data):
        """Update the state of the switch."""
        self.is_on = data.get("status")
        countdown = data.get("parameters")
        if countdown is not None:
            self._countdown_minutes = int(countdown)
        await self.publish_updates()
