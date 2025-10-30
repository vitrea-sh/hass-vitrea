from .base import BaseDevice
from ..control_api.commands import (
    BlindLocationCommand,
    BlindStopCommand,
    GetKeyStatusCommand,
)
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes


class Blind(BaseDevice):
    supported_key_types = [KeyTypes.BlindUp.value]

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        initial_location: int = 0,
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
        self._location = initial_location
        self.is_opening = False
        self.is_closing = False

    @property
    def is_closed(self) -> bool:
        return self.location == 0

    @property
    def location(self) -> int:
        return self._location

    @location.setter
    def location(self, value: int):
        if self._location != value:
            self.is_opening = False
            self.is_closing = False
        self._location = value

    async def set_location(
        self,
        location: int,
    ) -> bool:
        """Set the location of the blind."""
        if not 0 <= location <= 100:
            raise ValueError("Location must be between 0 and 100")
        await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=location
            ).serialize()
        )
        if self.location < location:
            self.is_opening = True
        else:
            self.is_closing = True
        return True

    async def stop(self) -> bool:
        """Stop the blind."""
        success = await self.controller.connection.send(
            BlindStopCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        if success:
            self.is_opening = False
            self.is_closing = False
        return True

    async def blind_up(self) -> bool:
        """Move the blind up."""
        success = await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=100
            ).serialize()
        )
        if success:
            self.is_opening = True
        return True

    async def blind_down(self) -> bool:
        """Move the blind down."""
        success = await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=0
            ).serialize()
        )
        if success:
            self.is_closing = True
        return True

    async def get_state(self):
        await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def update_state(self, data):
        """Update the state of the cover."""
        location = int(data.get("parameters"))
        self.location = location
        await self.publish_updates()
