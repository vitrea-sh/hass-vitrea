from datetime import datetime
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .hub import PushButton
import logging


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        PushButtonSensor(device)
        for device in hub.devices.values()
        if isinstance(device, PushButton)
    )


class PushButtonSensor(BinarySensorEntity):
    _attr_device_class = None
    _attr_icon = "mdi:gesture-tap-button"

    def __init__(self, push_button):
        self._push_button = push_button
        self._attr_name = push_button.name
        self._attr_unique_id = (
            f"{push_button.hub.hub_id}-{push_button.node_id}-{push_button.key_id}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": push_button.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Push Button",
        }

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self._push_button.is_on

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._push_button.hub.online

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._push_button.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._push_button.remove_callback(self.schedule_update_ha_state)
