"""Home Assistant switch entities for Vitrea."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_platform,
    config_validation as cv,
)
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MULTIWAY_SUBENTRY_TYPES
from .entity_debug import log_actuation
from .hub import SatelliteButton, Switch, PushButton
import voluptuous as vol


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: entity_platform.AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    link_manager = hass.data[DOMAIN].get(f"{config_entry.entry_id}_links")
    if link_manager is not None and any(
        subentry.subentry_type in MULTIWAY_SUBENTRY_TYPES
        for subentry in config_entry.subentries.values()
    ):
        async_add_entities([VitreaMultiwayKillSwitch(hub, link_manager)])
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
            vol.Required("minutes", default=0): cv.positive_int,
        },
        "async_turn_on_with_timer",
    )


class VitreaMultiwayKillSwitch(SwitchEntity, RestoreEntity):
    """Master kill-switch for all Multiway links.

    Turning it off tears every link down instantly — no key events, no
    LED writes, no service calls can leak through while paused. Turning
    it on rebuilds the links via the normal (record-only, warmed-up)
    setup path, so resuming never actuates anything by itself. The state
    is restored across restarts: links paused during an incident stay
    paused until someone deliberately resumes them.
    """

    _attr_should_poll = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub, link_manager):
        """Initialize the kill-switch."""
        self._manager = link_manager
        self._attr_name = "Multiway Links"
        self._attr_unique_id = f"{hub.hub_id}-multiway-links-enabled"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{hub.hub_id}-multiway")},
            "name": "Vitrea Multiway",
            "manufacturer": "Vitrea",
            "model": "Multiway links",
            "entry_type": DeviceEntryType.SERVICE,
        }

    async def async_added_to_hass(self) -> None:
        """Restore the paused state before the links are built."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "off":
            self._manager.restore_paused()

    @property
    def is_on(self):
        """Return true while the links are active."""
        return self._manager.enabled

    @property
    def icon(self):
        """Broken-link icon while paused."""
        return "mdi:link-variant" if self.is_on else "mdi:link-variant-off"

    @property
    def available(self) -> bool:
        """The kill-switch must work even while the hub is offline."""
        return True

    async def async_turn_on(self, **kwargs):
        """Resume all Multiway links."""
        log_actuation(self, "multiway.resume")
        await self._manager.async_set_enabled(True)
        self.async_write_ha_state()
        return True

    async def async_turn_off(self, **kwargs):
        """Pause all Multiway links."""
        log_actuation(self, "multiway.pause")
        await self._manager.async_set_enabled(False)
        self.async_write_ha_state()
        return True


class VitreaSwitch(SwitchEntity):
    """Representation of a Vitrea Switch for Home Assistant."""

    _attr_should_poll = False
    _attr_icon = "mdi:light-switch"

    def __init__(self, switch: Switch):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = switch.name
        self._attr_unique_id = f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": switch.name,
            "manufacturer": "Vitrea",
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
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._switch.hub.online

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        log_actuation(self, "switch.turn_on")
        await self._switch.turn_on()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        log_actuation(self, "switch.turn_off")
        await self._switch.turn_off()
        return True

    @property
    def is_on(self):
        """Return true if the switch is on."""
        return self._switch.is_on


class VitreaSatelliteIndicatorLed(SwitchEntity):
    """Representation of a Vitrea Satellite Indicator Led.

    The vBox only acknowledges the L command — it never pushes LED state,
    so the entity state is assumed from the last command we sent.
    """

    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(self, switch: SatelliteButton):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = f"{switch.name} Indicator"
        self._attr_unique_id = (
            f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}-indicator-led"
        )
        # Attach to the same device as the satellite sensor entity.
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}")
            },
            "name": switch.name,
            "manufacturer": "Vitrea",
        }

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._switch.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._switch.remove_callback(self.schedule_update_ha_state)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        log_actuation(self, "indicator.turn_on")
        await self._switch.turn_on_indicator()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        log_actuation(self, "indicator.turn_off")
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
    """Representation of a Vitrea Push Button Indicator Led.

    Assumed state: the vBox acknowledges the L command but never pushes
    LED state updates.
    """

    _attr_should_poll = False
    _attr_assumed_state = True

    def __init__(self, switch: PushButton):
        """Initialize the switch."""
        self._switch = switch
        self._attr_name = f"{switch.name} Indicator"
        self._attr_unique_id = (
            f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}-indicator-led"
        )
        # Attach to the same device as the push-button binary sensor.
        self._attr_device_info = {
            "identifiers": {
                (DOMAIN, f"{switch.hub.hub_id}-{switch.node_id}-{switch.key_id}")
            },
            "name": switch.name,
            "manufacturer": "Vitrea",
        }

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        self._switch.register_callback(self.schedule_update_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Entity being removed from hass."""
        self._switch.remove_callback(self.schedule_update_ha_state)

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        log_actuation(self, "indicator.turn_on")
        await self._switch.turn_on_indicator()
        return True

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        log_actuation(self, "indicator.turn_off")
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
