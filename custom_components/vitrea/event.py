"""Event entities for Vitrea satellite buttons.

Unlike the state-based sensor, an event entity fires once per physical
press — including repeated Short presses in quick succession, which a
state trigger cannot distinguish.
"""

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .hub import SatelliteButton


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Vitrea satellite button events."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaSatelliteEvent(device)
        for device in hub.devices.values()
        if isinstance(device, SatelliteButton)
    )


class VitreaSatelliteEvent(EventEntity):
    """Fires an event for every satellite button press."""

    _attr_should_poll = False
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = ["Short", "Long", "Release"]

    def __init__(self, satellite: SatelliteButton):
        """Initialize the event entity."""
        self._satellite = satellite
        self._baseline_generation: int | None = None
        self._attr_name = f"{satellite.name} Button"
        self._attr_unique_id = (
            f"{satellite.hub.hub_id}-{satellite.node_id}-{satellite.key_id}-event"
        )
        # Same device as the satellite sensor entity.
        self._attr_device_info = {
            "identifiers": {
                (
                    DOMAIN,
                    f"{satellite.hub.hub_id}-{satellite.node_id}-{satellite.key_id}",
                )
            },
            "name": satellite.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Satellite",
        }

    @property
    def available(self) -> bool:
        """Return True if the hub is available."""
        return self._satellite.hub.online

    async def async_added_to_hass(self) -> None:
        """Register for raw button events."""
        self._satellite.register_event_callback(self._handle_button_event)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._satellite.remove_event_callback(self._handle_button_event)

    @callback
    def _handle_button_event(self, event_type: str) -> None:
        """Dispatch a button press as an HA event."""
        generation = self._satellite.hub.connection_generation
        if generation != self._baseline_generation:
            # First report since a (re)connect. The status poll reports
            # every satellite key as "Release"; that is the key's resting
            # state, not a press, and must not fire on every restart.
            self._baseline_generation = generation
            if event_type == "Release":
                return
        self._trigger_event(event_type)
        self.schedule_update_ha_state()
