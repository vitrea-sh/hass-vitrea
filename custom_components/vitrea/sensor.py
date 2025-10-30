from datetime import datetime
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import StrEnum
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .hub import SatelliteButton
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
        SatelliteSensor(device)
        for device in hub.devices.values()
        if isinstance(device, SatelliteButton)
    )


class SatelliteSensor(SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["Short", "Long", "Release"]
    _attr_last_reset: datetime | None = None
    _attr_icon = "mdi:gesture-double-tap"

    def __init__(self, satellite):
        self._satellite = satellite
        self._attr_name = satellite.name
        self._attr_unique_id = (
            f"{satellite.hub.hub_id}-{satellite.node_id}-{satellite.key_id}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": satellite.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Satellite",
        }

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        return self._satellite.native_value

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._satellite.hub.online

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._satellite.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._satellite.remove_callback(self.schedule_update_ha_state)
