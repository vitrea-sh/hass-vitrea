import logging
from typing import Callable
from ..utils.enums import KeyTypes
from ..vbox_controller import VBoxController

_LOGGER = logging.getLogger(__name__)


class BaseDevice:
    def __init__(
        self,
        node_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        append_room_to_name: bool = True,
        add_timer: bool = False,
    ):
        self.node_id = node_id
        self.key_name = key_name
        self.room_name = room_name
        if append_room_to_name:
            self.name = f"{room_name} {key_name}"
        else:
            self.name = key_name
        self._callbacks = set()
        self.controller = controller
        self.add_timer = add_timer

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

    async def get_state(self):
        raise NotImplementedError

    @property
    def _id(self):
        key_id = getattr(self, "key_id", None)
        if key_id is None:
            return f"N{self.node_id:03d}"
        return f"N{self.node_id:03d}-{self.key_id}"

    @property
    def supported_key_types(self) -> list[KeyTypes]:
        """Return list of supported key types for this device object."""
        raise NotImplementedError
