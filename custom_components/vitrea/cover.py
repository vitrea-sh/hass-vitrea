from typing import Any
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.cover import (
    CoverEntity,
    CoverDeviceClass,
    CoverEntityFeature,
)

from .const import DOMAIN
from .hub import Cover


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaCover(device)
        for device in hub.devices.values()
        if isinstance(device, Cover)
    )


class VitreaCover(CoverEntity):
    _attr_should_poll = False
    _attr_device_class = CoverDeviceClass.BLIND
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, cover: Cover):
        self._cover = cover
        self._attr_name = cover.name
        self._attr_unique_id = f"{cover.hub.hub_id}-{cover.node_id}-{cover.key_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": cover.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Blind",
        }

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._cover.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._cover.remove_callback(self.schedule_update_ha_state)

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._cover.hub.online

    @property
    def device_info(self):
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._cover._id)},
            # If desired, the name for the device could be different to the entity
            "name": self._attr_name,
            "manufacturer": self._cover.hub.manufacturer,
        }

    @property
    def current_cover_position(self):
        return self._cover.current_cover_position

    @property
    def is_closed(self):
        return self._cover.is_closed

    @property
    def is_opening(self):
        return self._cover.is_opening

    @property
    def is_closing(self):
        return self._cover.is_closing

    async def async_open_cover(self, **kwargs):
        await self._cover.blind_up()

    async def async_close_cover(self, **kwargs):
        await self._cover.blind_down()

    async def async_stop_cover(self, **kwargs):
        await self._cover.stop()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._cover.set_location(kwargs["position"])
