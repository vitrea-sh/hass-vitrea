import logging
import time

from .base import BaseDevice
from ..control_api.commands import (
    BlindLocationCommand,
    BlindStopCommand,
    GetKeyStatusCommand,
)
from ..vbox_controller import VBoxController
from ..utils.enums import KeyTypes

_LOGGER = logging.getLogger(__name__)


class Blind(BaseDevice):
    supported_key_types = [KeyTypes.BlindUp.value]

    # A blind that never reports back within this window is assumed stopped;
    # prevents is_opening/is_closing from sticking forever on a lost command.
    MOVEMENT_TIMEOUT = 120.0

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
        self._is_opening = False
        self._is_closing = False
        self._movement_started = 0.0

    @property
    def is_closed(self) -> bool:
        return self.location == 0

    @property
    def is_opening(self) -> bool:
        return self._is_opening and not self._movement_expired()

    @property
    def is_closing(self) -> bool:
        return self._is_closing and not self._movement_expired()

    def _movement_expired(self) -> bool:
        return time.monotonic() - self._movement_started > self.MOVEMENT_TIMEOUT

    def _start_movement(self, *, opening: bool) -> None:
        self._is_opening = opening
        self._is_closing = not opening
        self._movement_started = time.monotonic()

    def _stop_movement(self) -> None:
        self._is_opening = False
        self._is_closing = False

    @property
    def location(self) -> int:
        return self._location

    @location.setter
    def location(self, value: int):
        self._location = value

    async def set_location(
        self,
        location: int,
    ) -> bool:
        """Set the location of the blind."""
        if not 0 <= location <= 100:
            raise ValueError("Location must be between 0 and 100")
        sent = await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=location
            ).serialize()
        )
        if sent:
            self._start_movement(opening=self.location < location)
        return bool(sent)

    async def stop(self) -> bool:
        """Stop the blind."""
        await self.controller.connection.send(
            BlindStopCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        self._stop_movement()
        return True

    async def blind_up(self) -> bool:
        """Move the blind up."""
        sent = await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=100
            ).serialize()
        )
        if sent:
            self._start_movement(opening=True)
        return True

    async def blind_down(self) -> bool:
        """Move the blind down."""
        sent = await self.controller.connection.send(
            BlindLocationCommand(
                node_id=self.node_id, key_id=self.key_id, location=0
            ).serialize()
        )
        if sent:
            self._start_movement(opening=False)
        return True

    async def get_state(self):
        await self.controller.connection.send(
            GetKeyStatusCommand(node_id=self.node_id, key_id=self.key_id).serialize()
        )
        return True

    async def update_state(self, data):
        """Update the state of the cover."""
        params = data.get("parameters")
        if params is None:
            _LOGGER.debug(
                "Ignoring blind status without location for %s: %s", self._id, data
            )
            return
        try:
            location = int(params)
        except (TypeError, ValueError):
            _LOGGER.warning("Invalid blind location for %s: %r", self._id, params)
            return
        # The controller sends a status frame once the command has finished
        # executing, so any position report means movement has ended — even
        # when the reported position equals the previous one.
        self._stop_movement()
        self.location = location
        await self.publish_updates()
