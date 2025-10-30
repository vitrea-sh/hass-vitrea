"""Home Assistant switch entities for Vitrea."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_platform,
    config_validation as cv,
)

from .const import DOMAIN, VitreaFeatures
from .hub import Switch
import voluptuous as vol


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: entity_platform.AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaSwitchCountdown(device)
        for device in hub.devices.values()
        if isinstance(device, Switch) and device.add_timer
    )


class VitreaSwitchCountdown(NumberEntity):
    """Representation of a Vitrea Switch for Home Assistant."""

    _attr_should_poll = False
    _attr_supported_features = [VitreaFeatures.TIMER_ON]
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 0
    _attr_native_max_value = 120
    _attr_native_step = 5

    def __init__(self, switch: Switch):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = f"{switch.name} Countdown"
        self._attr_unique_id = (
            f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}-countdown"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": f"{switch.name} Countdown",
            "manufacturer": "Vitrea",
            "model": "Vitrea Boiler Timer",
            "icon": "mdi:timer-outline",
        }

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._switch.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._switch.remove_callback(self.schedule_update_ha_state)

    async def async_turn_on_with_timer(self, minutes: int):
        """Turn the switch on with a timer."""
        await self._switch.turn_on(duration=minutes)
        return True

    @property
    def device_info(self):
        """Information about this entity/device."""
        return {
            "identifiers": {(DOMAIN, self._switch._id)},
            "name": self._attr_name,
            "manufacturer": self._switch.hub.manufacturer,
        }

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._switch.hub.online

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._switch.turn_on()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._switch.turn_off()
        return True

    @property
    def native_value(self) -> int:
        """Return the countdown minutes of the switch."""
        return self._switch.countdown_minutes

    async def async_set_native_value(self, value: int) -> None:
        """Set the countdown minutes of the switch."""
        if value == 0:
            await self._switch.turn_off()
            return
        await self._switch.turn_on(duration=int(value))
