"""The Vitrea integration."""

from __future__ import annotations

import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .hub import VitreaHub
from .multiway import LinkManager
from .vitrea_integration import supports_v95_features, validate_controller_availability

PLATFORMS: list[Platform] = [
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
    Platform.SENSOR,
    Platform.SCENE,
    Platform.CLIMATE,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.EVENT,
]

# Device identifiers used to be the bare key id ("N001-1"), which collides
# across two Vitrea hubs. They are now hub-scoped ("<hub_id>-1-1").
_LEGACY_DEVICE_ID = re.compile(r"^N(\d{3})-(\d+)$")


@callback
def _async_migrate_device_identifiers(
    hass: HomeAssistant, entry: ConfigEntry, hub: VitreaHub
) -> None:
    """Rewrite legacy device identifiers to hub-scoped ones."""
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        new_identifiers = set()
        changed = False
        for domain, identifier in device.identifiers:
            match = (
                _LEGACY_DEVICE_ID.match(identifier)
                if domain == DOMAIN and isinstance(identifier, str)
                else None
            )
            if match:
                node_id = int(match.group(1))
                key_id = int(match.group(2))
                new_identifiers.add((DOMAIN, f"{hub.hub_id}-{node_id}-{key_id}"))
                changed = True
            else:
                new_identifiers.add((domain, identifier))
        if not changed:
            continue
        if any(
            registry.async_get_device(identifiers={identifier})
            not in (None, device)
            for identifier in new_identifiers - device.identifiers
        ):
            # Target device already exists; entities re-attach to it via
            # their device_info, the legacy shell is left for HA cleanup.
            continue
        registry.async_update_device(device.id, new_identifiers=new_identifiers)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Vitrea from a config entry."""

    version = entry.data.get("controller_version")
    if version is None:
        # One-time backfill for entries created before the firmware version
        # was stored (uses a short-lived validation socket, then releases
        # the vBox's single slot before the main connection opens).
        probe = await validate_controller_availability(
            entry.data["ip"], entry.data["port"]
        )
        version = probe.get("version", "")
        if version:
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, "controller_version": version}
            )
    # Firmware 9.5 feature set: LED indicator control and Room-On groups.
    supports_v95 = (
        supports_v95_features(version)
        if version
        else entry.data.get("supports_led_commands", False)
    )
    hub = VitreaHub(
        hass=hass,
        host=entry.data["ip"],
        port=entry.data["port"],
        append_room_name=entry.data["append_room_to_name"],
        supports_led_commands=supports_v95,
        toggles_as_lights=entry.data.get("toggles_as_lights", False),
        supports_room_on=supports_v95,
    )
    filter_mw = entry.data.get("filter_mw", True)
    try:
        success, reason = await hub.read_gateway(filter_mw=filter_mw)
    except (ConnectionError, TimeoutError, OSError) as err:
        # Close before retrying, otherwise every ConfigEntryNotReady retry
        # leaks a connection plus its watchdog and background tasks.
        await hub.controller.close()
        raise ConfigEntryNotReady(str(err)) from err
    except Exception:
        # Any other failure would leave the entry in a failed state that
        # Home Assistant never unloads; do not keep the host slot.
        await hub.controller.close()
        raise
    if not success:
        await hub.controller.close()
        raise ConfigEntryNotReady(reason)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    _async_migrate_device_identifiers(hass, entry, hub)
    # Multiway links (config subentries): wall keys bound to HA entities.
    # The manager is created (but not yet started) before the platforms so
    # the kill-switch entity can restore a paused state ahead of the links
    # being built.
    link_manager = LinkManager(hass, entry, hub)
    hass.data[DOMAIN][f"{entry.entry_id}_links"] = link_manager
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await link_manager.async_setup()
    except Exception:
        # A failed setup is not unloaded by Home Assistant, so release the
        # controller's single host slot here instead of holding it forever.
        hass.data[DOMAIN].pop(f"{entry.entry_id}_links", None)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        await hub.controller.close()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its data or subentries change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    link_manager = hass.data.get(DOMAIN, {}).pop(f"{entry.entry_id}_links", None)
    if link_manager is not None:
        await link_manager.async_teardown()
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hub = hass.data[DOMAIN].pop(entry.entry_id)
        await hub.controller.close()
    return unload_ok
