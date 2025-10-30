"""Home Assistant switch entities for Vitrea."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_platform,
    service,
    device_registry,
    config_validation as cv,
)

from .const import DOMAIN, VitreaFeatures
from .hub import SatelliteButton, Switch, PushButton
import voluptuous as vol


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: entity_platform.AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaSwitch(device)
        for device in hub.devices.values()
        if isinstance(device, Switch)
    )
    if hub.supports_led_commands:
        async_add_entities(
            VitreaSatelliteIndicatorLed(device)
            for device in hub.devices.values()
            if isinstance(device, SatelliteButton)
        )
        async_add_entities(
            VitreaPushButtonIndicatorLed(device)
            for device in hub.devices.values()
            if isinstance(device, PushButton)
        )
    platform = entity_platform.current_platform.get()
    platform.async_register_entity_service(
        "turn_on_with_timer",
        {
            vol.Required("entity_id"): cv.entity_id,
            vol.Required("minutes", default=0): cv.positive_int,
        },
        "async_turn_on_with_timer",
    )


class VitreaSwitch(SwitchEntity):
    """Representation of a Vitrea Switch for Home Assistant."""

    _attr_should_poll = False
    _attr_supported_features = [VitreaFeatures.TIMER_ON]

    def __init__(self, switch: Switch):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = switch.name
        self._attr_unique_id = f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": switch.name,
            "manufacturer": "Vitrea",
            "icon": "mdi:light-switch",
            "model": "Vitrea Toggle",
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
            # If desired, the name for the device could be different to the entity
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
    def is_on(self):
        """Return true if the switch is on."""
        return self._switch.is_on


class VitreaSatelliteIndicatorLed(SwitchEntity):
    """Representation of a Vitrea Satellite Indicator Led."""

    _attr_should_poll = False
    _attr_supported_features = []

    def __init__(self, switch: SatelliteButton):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = switch.name
        self._attr_unique_id = (
            f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}-indicator-led"
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._switch.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._switch.remove_callback(self.schedule_update_ha_state)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._switch.turn_on_indicator()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._switch.turn_off_indicator()
        return True

    @property
    def is_on(self):
        """Return true if the switch is on."""
        return self._switch.indicator_value

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._switch.hub.online


class VitreaPushButtonIndicatorLed(SwitchEntity):
    """Representation of a Vitrea Satellite Indicator Led."""

    _attr_should_poll = False
    _attr_supported_features = []

    def __init__(self, switch: PushButton):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = switch.name
        self._attr_unique_id = (
            f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}-indicator-led"
        )

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._switch.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._switch.remove_callback(self.schedule_update_ha_state)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._switch.turn_on_indicator()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._switch.turn_off_indicator()
        return True

    @property
    def is_on(self):
        """Return true if the switch is on."""
        return self._switch.indicator_value

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._switch.hub.online
