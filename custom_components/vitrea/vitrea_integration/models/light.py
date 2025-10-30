from .base import BaseDevice
from ..control_api.commands import (
    DimmerIntensityCommand,
    DimmerStopCommand,
    DimmerRecallLastCommand,
    GetKeyStatusCommand,
)
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes
import logging

_LOGGER = logging.getLogger(__name__)


class Dimmer(BaseDevice):
    supported_key_types = [KeyTypes.Dimmer.value]

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        initial_state: bool = False,
        initial_intensity: int = 0,
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
        self._intensity = initial_intensity

    @property
    def state(self) -> bool:
        return self._state

    @property
    def intensity(self) -> int:
        return self._intensity

    @intensity.setter
    def intensity(self, value: int):
        if not 0 <= value <= 100:
            raise ValueError("Intensity must be between 0 and 100")
        self._intensity = value

    @property
    def is_on(self) -> bool:
        """Return the state of the light."""
        return self.intensity > 0

    async def set_intensity(
        self,
        intensity: int,
    ) -> bool:
        """Set the intensity of the light."""
        if not 0 <= intensity <= 100:
            raise ValueError("Intensity must be between 0 and 100")
        await self.controller.connection.send(
            DimmerIntensityCommand(
                node_id=self.node_id, key_id=self.key_id, intensity=intensity
            ).serialize()
        )
        return True

    async def stop(self) -> bool:
        """Stop the light during dimming."""
        await self.controller.connection.send(
            DimmerStopCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def turn_on(self) -> bool:
        """Turn on the light."""
        await self.controller.connection.send(
            DimmerRecallLastCommand(
                node_id=self.node_id, key_id=self.key_id
            ).serialize()
        )
        return True

    async def turn_off(self) -> bool:
        """Turn off the light."""
        await self.controller.connection.send(
            DimmerIntensityCommand(
                node_id=self.node_id, key_id=self.key_id, intensity=0
            ).serialize()
        )
        return True

    async def get_state(self):
        await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def update_state(self, data):
        """Update the state of the light."""
        intensity = int(data.get("parameters"))
        self.intensity = intensity
        await self.publish_updates()
