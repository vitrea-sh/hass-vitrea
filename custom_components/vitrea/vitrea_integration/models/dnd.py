from ..control_api.commands import DNDSetStatus, DNDStatus, GetKeyStatusCommand
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes

from .base import BaseDevice
# Validate Duration, supported key types and state


class DNDKeypad(BaseDevice):
    supported_key_types = [
        KeyTypes.DND
    ]

    def __init__(
        self,
        node_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        key_id: int = 1,
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
        self._dnd = False
        self._mur = False

    @property
    def state(self) -> bool:
        return self._state
    
    @property
    def is_dnd_on(self) -> bool:
        return self._dnd
    
    @property
    def is_mur_on(self) -> bool:
        return self._mur

    async def set_status(self, status: DNDStatus) -> bool:
        if not isinstance(status, DNDStatus):
            raise ValueError("Status must be an instance of DNDStatus.")
        await self.controller.connection.send(
            DNDSetStatus(node_id=self.node_id, status=status).serialize()
        )
        return True

    async def get_state(self):
        await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=1).serialize()
        )
        return True

    async def update_state(self, data):
        """Update the state of the switch."""
        dnd_status = DNDStatus(int(data.get("params", "9")))
        match dnd_status:
            case DNDStatus.OFF:
                self._dnd = False
                self._mur = False
            case DNDStatus.DND:
                self._dnd = True
                self._mur = False
            case DNDStatus.MUR:
                self._dnd = False
                self._mur = True
            case _:
                self._dnd = False
                self._mur = False
        await self.publish_updates()
