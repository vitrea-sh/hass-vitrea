"""Home Assistant - Vitrea Dimmer Light."""

import logging
import math
from typing import Any, Union

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)

from .const import DOMAIN, VitreaFeatures
from .hub import Light

_LOGGER = logging.getLogger(__name__)
BRIGHTNESS_SCALE = (1, 255)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaLight(device)
        for device in hub.devices.values()
        if isinstance(device, Light)
    )


class VitreaLight(LightEntity):
    """Representation of a Vitrea Light for Home Assistant."""

    _attr_should_poll = False

    def __init__(self, light: Light):
        """Initialize the light."""
        self._light = light
        self._attr_name = light.name
        self._attr_unique_id = f"{light.hub.hub_id}-{light.node_id}-{light.key_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": light.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Dimmer",
        }

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._light.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._light.remove_callback(self.schedule_update_ha_state)

    @property
    def device_info(self):
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._light._id)},
            # If desired, the name for the device could be different to the entity
            "name": self._attr_name,
            "manufacturer": self._light.hub.manufacturer,
        }

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._light.hub.online

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        intensity = math.ceil(
            ranged_value_to_percentage(
                BRIGHTNESS_SCALE, kwargs.get(ATTR_BRIGHTNESS, 255)
            )
        )
        _LOGGER.debug("Intensity: %s", intensity)
        await self._light.set_intensity(intensity)

    async def async_turn_off(self) -> None:
        """Turn the light off."""
        await self._light.turn_off()

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._light.is_on

    @property
    def brightness(self) -> int:
        """Return the brightness of the light."""
        return percentage_to_ranged_value(BRIGHTNESS_SCALE, self._light.intensity)

    @property
    def supported_color_modes(self) -> Union[set[ColorMode], set[str], set[None]]:
        """Flag supported color modes."""
        return {ColorMode.BRIGHTNESS}

    @property
    def color_mode(self) -> Union[ColorMode, str, None]:
        """Return the color mode of the light."""
        return ColorMode.BRIGHTNESS
