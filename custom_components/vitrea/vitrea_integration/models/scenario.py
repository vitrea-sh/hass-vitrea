from typing import Callable
from ..control_api.commands import ScenarioCommand
from ..vbox_controller import VBoxController
import logging

_LOGGER = logging.getLogger(__name__)


class Scenario:
    supported_key_types = []

    def __init__(
        self,
        scene_id: int,
        scene_name: str,
        room_name: str,
        controller: VBoxController,
        append_room_to_name: bool = True,
        **kwargs,
    ):
        self.scene_id = scene_id
        self.scene_name = scene_name
        self.room_name = room_name
        self.controller = controller
        self._callbacks = set()
        if append_room_to_name:
            self.name = f"{room_name} {scene_name}"
        else:
            self.name = scene_name

    @property
    def _id(self):
        return f"R{self.scene_id:03d}"

    async def run(self) -> bool:
        await self.controller.connection.send(
            ScenarioCommand(scenario_id=self.scene_id).serialize()
        )
        return True

    def register_callback(self, callback: Callable[[], None]) -> None:
        """Register callback, called when Switch changes state."""
        self._callbacks.add(callback)

    def remove_callback(self, callback: Callable[[], None]) -> None:
        """Remove previously registered callback."""
        self._callbacks.discard(callback)

    async def publish_updates(self, *args, **kwargs) -> None:
        """Schedule call all registered callbacks."""
        _LOGGER.debug("Publishing updates for %s", self._id)
        for callback in self._callbacks:
            callback(*args, **kwargs)
