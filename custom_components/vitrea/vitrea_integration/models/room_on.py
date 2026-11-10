from ..utils.enums import KeyTypes
from .toggle import Toggle


class RoomOn(Toggle):
    """A Room-On key: switches a vBox-side group of lights (firmware 9.5+).

    On the wire it behaves exactly like a toggle key — O/F/T commands and
    O/F status frames — the grouping logic lives inside the controller.
    """

    supported_key_types = [KeyTypes.RoomOn.value]
