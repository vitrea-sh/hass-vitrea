"""The Vitrea integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN
from .hub import VitreaHub

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
    Platform.SENSOR,
    Platform.SCENE,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vitrea from a config entry."""

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = VitreaHub(
        hass=hass,
        host=entry.data["ip"],
        port=entry.data["port"],
        append_room_name=entry.data["append_room_to_name"],
        supports_led_commands=entry.data.get("supports_led_commands", False),
    )
    filter_mw = entry.data.get("filter_mw", True)
    success, reason = await hass.data[DOMAIN][entry.entry_id].read_gateway(
        filter_mw=filter_mw
    )
    if not success:
        raise ConfigEntryNotReady(reason)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.controller.close()
    return unload_ok
