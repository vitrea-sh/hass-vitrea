"""Provides device triggers for Vitrea."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.homeassistant.triggers import state as state_trigger
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_PLATFORM,
    CONF_TYPE,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from . import DOMAIN

TRIGGER_TYPES = {"Short", "Long", "Release"}

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_ENTITY_ID): cv.entity_id,
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List device triggers for Vitrea devices."""
    registry = er.async_get(hass)
    triggers = []
    # Offer Short/Long/Release triggers for every satellite sensor entity
    # of this device (detected via its ENUM options).
    for entry in er.async_entries_for_device(registry, device_id):
        if entry.platform != DOMAIN:
            continue
        base_trigger = {
            CONF_PLATFORM: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_ENTITY_ID: entry.entity_id,
        }
        if not entry.capabilities:
            continue
        options = entry.capabilities.get("options", [])
        if not options:
            options = []
        if "Short" in options:
            triggers.append({**base_trigger, CONF_TYPE: "Short"})
        if "Long" in options:
            triggers.append({**base_trigger, CONF_TYPE: "Long"})
        if "Release" in options:
            triggers.append({**base_trigger, CONF_TYPE: "Release"})
    return triggers


async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger."""
    if config[CONF_TYPE] == "Short":
        to_state = "Short"
    elif config[CONF_TYPE] == "Long":
        to_state = "Long"
    elif config[CONF_TYPE] == "Release":
        to_state = "Release"
    else:
        return None
    state_config = {
        state_trigger.CONF_PLATFORM: "state",
        CONF_ENTITY_ID: config[CONF_ENTITY_ID],
        state_trigger.CONF_TO: to_state,
    }
    state_config = await state_trigger.async_validate_trigger_config(hass, state_config)
    return await state_trigger.async_attach_trigger(
        hass, state_config, action, trigger_info, platform_type="device"
    )
