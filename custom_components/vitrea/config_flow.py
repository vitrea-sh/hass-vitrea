"""Config flow for Vitrea integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    CONF_DOWN_KEY_ID,
    CONF_KEY_ID,
    CONF_LONG_PRESS_SCENE,
    CONF_MAX_BRIGHTNESS,
    CONF_MIN_BRIGHTNESS,
    CONF_SATELLITE_ID,
    CONF_STEP_DELAY,
    CONF_STEP_PCT,
    CONF_TARGET_ENTITY,
    CONF_TARGET_ENTITY_ID,
    CONF_TILT_STEP,
    CONF_TOGGLE_ID,
    CONF_TRAVEL_TIME,
    CONF_UP_KEY_ID,
    DOMAIN,
    SUBENTRY_TYPE_BLIND_LINK,
    SUBENTRY_TYPE_CLIMATE_LINK,
    SUBENTRY_TYPE_SATELLITE_LIGHT_LINK,
    SUBENTRY_TYPE_SATELLITE_LINK,
    SUBENTRY_TYPE_TOGGLE_LINK,
)
from .vitrea_integration import validate_controller_availability

_LOGGER = logging.getLogger(__name__)


def _stored_target(hass, entity_id: str) -> str:
    """Persist targets as entity-registry UUIDs so links survive renames."""
    registry_entry = er.async_get(hass).async_get(entity_id)
    return registry_entry.id if registry_entry else entity_id

# Retryable problems re-show the form with an error; anything else
# (e.g. unsupported firmware) aborts the flow.
RETRYABLE_REASONS = {"connection_error", "auth_failed"}


class VitreaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Vitrea Config Flow."""

    VERSION = 1
    MINOR_VERSION = 1

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return Multiway link subentry flows."""
        return {
            SUBENTRY_TYPE_SATELLITE_LINK: SatelliteLinkFlow,
            SUBENTRY_TYPE_SATELLITE_LIGHT_LINK: SatelliteLightLinkFlow,
            SUBENTRY_TYPE_CLIMATE_LINK: ClimateLinkFlow,
            SUBENTRY_TYPE_BLIND_LINK: BlindLinkFlow,
            SUBENTRY_TYPE_TOGGLE_LINK: ToggleLinkFlow,
        }
    STEP_USER_DATA_SCHEMA = vol.Schema(
        {
            vol.Required("ip"): str,
            vol.Required("port", default=11502): int,
            vol.Required("append_room_to_name", default=True): bool,
            vol.Required("filter_mw", default=True): bool,
            vol.Required("toggles_as_lights", default=False): bool,
        }
    )

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Check first if not already configured
            await self.async_set_unique_id(user_input.get("ip"))
            self._abort_if_unique_id_configured()
            result = await validate_controller_availability(
                user_input.get("ip"), user_input.get("port")
            )
            _LOGGER.debug(result)
            if result.get("supported", False):
                return self.async_create_entry(
                    title="Vitrea Gateway",
                    data={
                        **user_input,
                        "supports_led_commands": result.get(
                            "supports_led_commands", False
                        ),
                        "controller_version": result.get("version", ""),
                    },
                )
            reason = result.get("reason") or "connection_error"
            if reason not in RETRYABLE_REASONS:
                return self.async_abort(
                    reason=reason,
                    description_placeholders=result,
                )
            errors["base"] = reason
        return self.async_show_form(
            step_id="user",
            data_schema=self.STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class SatelliteLinkFlow(ConfigSubentryFlow):
    """Link a satellite button to any toggleable entity (LED follows it)."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a satellite link."""
        entry = self._get_entry()
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if hub is None:
            return self.async_abort(reason="hub_not_available")

        satellite_options = _satellite_options(hub)
        if not satellite_options:
            return self.async_abort(reason="no_satellites")

        if user_input is not None:
            satellite_id = user_input[CONF_SATELLITE_ID]
            target = user_input[CONF_TARGET_ENTITY]
            if _satellite_taken(entry, satellite_id):
                return self.async_abort(reason="already_configured")
            satellite = hub.devices.get(satellite_id)
            data = {
                **user_input,
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            return self.async_create_entry(
                data=data, title=f"{satellite.name} → {target}"
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SATELLITE_ID): SelectSelector(
                        SelectSelectorConfig(options=satellite_options)
                    ),
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig()
                    ),
                    vol.Optional(CONF_LONG_PRESS_SCENE): EntitySelector(
                        EntitySelectorConfig(domain="scene")
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change the target of an existing satellite link."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            target = user_input[CONF_TARGET_ENTITY]
            data = dict(subentry.data) | {
                **user_input,
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            title = f"{subentry.title.split(' → ')[0]} → {target}"
            return self.async_update_reload_and_abort(
                entry, subentry, data=data, title=title
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig()
                    ),
                    vol.Optional(CONF_LONG_PRESS_SCENE): EntitySelector(
                        EntitySelectorConfig(domain="scene")
                    ),
                }
            ),
        )


class SatelliteLightLinkFlow(ConfigSubentryFlow):
    """Link a satellite button to a light with hold-to-dim."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a satellite light link."""
        entry = self._get_entry()
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if hub is None:
            return self.async_abort(reason="hub_not_available")

        satellite_options = _satellite_options(hub)
        if not satellite_options:
            return self.async_abort(reason="no_satellites")

        errors: dict[str, str] = {}
        if user_input is not None:
            satellite_id = user_input[CONF_SATELLITE_ID]
            target = user_input[CONF_TARGET_ENTITY]
            if _satellite_taken(entry, satellite_id):
                return self.async_abort(reason="already_configured")
            if user_input[CONF_MIN_BRIGHTNESS] >= user_input[CONF_MAX_BRIGHTNESS]:
                errors["base"] = "invalid_brightness_range"
            else:
                satellite = hub.devices.get(satellite_id)
                data = {
                    **user_input,
                    CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                    CONF_TARGET_ENTITY_ID: target,
                }
                return self.async_create_entry(
                    data=data, title=f"{satellite.name} → {target}"
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self._schema(satellite_options),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change the target or dimming parameters of a light link."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_MIN_BRIGHTNESS] >= user_input[CONF_MAX_BRIGHTNESS]:
                errors["base"] = "invalid_brightness_range"
            else:
                target = user_input[CONF_TARGET_ENTITY]
                data = dict(subentry.data) | {
                    **user_input,
                    CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                    CONF_TARGET_ENTITY_ID: target,
                }
                title = f"{subentry.title.split(' → ')[0]} → {target}"
                return self.async_update_reload_and_abort(
                    entry, subentry, data=data, title=title
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self._schema(None, subentry.data),
            errors=errors,
        )

    @staticmethod
    def _schema(satellite_options, defaults: dict | None = None) -> vol.Schema:
        defaults = defaults or {}
        fields: dict = {}
        if satellite_options is not None:
            fields[vol.Required(CONF_SATELLITE_ID)] = SelectSelector(
                SelectSelectorConfig(options=satellite_options)
            )
        fields.update(
            {
                vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                    EntitySelectorConfig(domain="light")
                ),
                vol.Required(
                    CONF_MIN_BRIGHTNESS, default=defaults.get(CONF_MIN_BRIGHTNESS, 1)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_MAX_BRIGHTNESS, default=defaults.get(CONF_MAX_BRIGHTNESS, 100)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_STEP_PCT, default=defaults.get(CONF_STEP_PCT, 5)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=25,
                        step=1,
                        unit_of_measurement="%",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
                vol.Required(
                    CONF_STEP_DELAY, default=defaults.get(CONF_STEP_DELAY, 300)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=50,
                        max=1000,
                        step=50,
                        unit_of_measurement="ms",
                        mode=NumberSelectorMode.SLIDER,
                    )
                ),
            }
        )
        return vol.Schema(fields)


class ClimateLinkFlow(ConfigSubentryFlow):
    """Link a Vitrea key (satellite button OR toggle) to a climate device."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a climate link."""
        entry = self._get_entry()
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if hub is None:
            return self.async_abort(reason="hub_not_available")

        key_options = _climate_source_options(hub)
        if not key_options:
            return self.async_abort(reason="no_keys")

        if user_input is not None:
            key_id = user_input[CONF_KEY_ID]
            target = user_input[CONF_TARGET_ENTITY]
            if _source_key_taken(entry, key_id):
                return self.async_abort(reason="already_configured")
            source = hub.devices.get(key_id)
            data = {
                **user_input,
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            return self.async_create_entry(
                data=data, title=f"{source.name} → {target}"
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_KEY_ID): SelectSelector(
                        SelectSelectorConfig(options=key_options)
                    ),
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="climate")
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change the target of a climate link."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            target = user_input[CONF_TARGET_ENTITY]
            data = dict(subentry.data) | {
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            title = f"{subentry.title.split(' → ')[0]} → {target}"
            return self.async_update_reload_and_abort(
                entry, subentry, data=data, title=title
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="climate")
                    ),
                }
            ),
        )


class BlindLinkFlow(ConfigSubentryFlow):
    """Link a pair of satellite buttons (up/down) to a cover entity."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a blind link."""
        entry = self._get_entry()
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if hub is None:
            return self.async_abort(reason="hub_not_available")

        satellite_options = _satellite_options(hub)
        if len(satellite_options) < 2:
            return self.async_abort(reason="no_satellites")

        errors: dict[str, str] = {}
        if user_input is not None:
            up_key = user_input[CONF_UP_KEY_ID]
            down_key = user_input[CONF_DOWN_KEY_ID]
            target = user_input[CONF_TARGET_ENTITY]
            if up_key == down_key:
                errors["base"] = "same_key"
            elif _source_key_taken(entry, up_key) or _source_key_taken(
                entry, down_key
            ):
                return self.async_abort(reason="already_configured")
            else:
                up = hub.devices.get(up_key)
                data = {
                    **user_input,
                    CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                    CONF_TARGET_ENTITY_ID: target,
                }
                return self.async_create_entry(
                    data=data, title=f"{up.name} ↕ {target}"
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UP_KEY_ID): SelectSelector(
                        SelectSelectorConfig(options=satellite_options)
                    ),
                    vol.Required(CONF_DOWN_KEY_ID): SelectSelector(
                        SelectSelectorConfig(options=satellite_options)
                    ),
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="cover")
                    ),
                    vol.Required(CONF_TILT_STEP, default=10): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50,
                            step=1,
                            unit_of_measurement="%",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(CONF_TRAVEL_TIME, default=30): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=120,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change the target or tilt step of a blind link."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            target = user_input[CONF_TARGET_ENTITY]
            data = dict(subentry.data) | {
                **user_input,
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            title = f"{subentry.title.split(' ↕ ')[0]} ↕ {target}"
            return self.async_update_reload_and_abort(
                entry, subentry, data=data, title=title
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig(domain="cover")
                    ),
                    vol.Required(
                        CONF_TILT_STEP,
                        default=subentry.data.get(CONF_TILT_STEP, 10),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=50,
                            step=1,
                            unit_of_measurement="%",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_TRAVEL_TIME,
                        default=subentry.data.get(CONF_TRAVEL_TIME, 30),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=5,
                            max=120,
                            step=1,
                            unit_of_measurement="s",
                            mode=NumberSelectorMode.SLIDER,
                        )
                    ),
                }
            ),
        )


class ToggleLinkFlow(ConfigSubentryFlow):
    """Bidirectionally link a regular toggle key to any entity."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Create a toggle link."""
        entry = self._get_entry()
        hub = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
        if hub is None:
            return self.async_abort(reason="hub_not_available")

        toggle_options = _toggle_options(hub)
        if not toggle_options:
            return self.async_abort(reason="no_toggles")

        if user_input is not None:
            toggle_id = user_input[CONF_TOGGLE_ID]
            target = user_input[CONF_TARGET_ENTITY]
            for subentry in entry.subentries.values():
                if (
                    subentry.subentry_type == SUBENTRY_TYPE_TOGGLE_LINK
                    and subentry.data.get(CONF_TOGGLE_ID) == toggle_id
                ):
                    return self.async_abort(reason="already_configured")
            toggle = hub.devices.get(toggle_id)
            data = {
                **user_input,
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            return self.async_create_entry(
                data=data, title=f"{toggle.name} ↔ {target}"
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TOGGLE_ID): SelectSelector(
                        SelectSelectorConfig(options=toggle_options)
                    ),
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig()
                    ),
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change the target of an existing toggle link."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()

        if user_input is not None:
            target = user_input[CONF_TARGET_ENTITY]
            data = dict(subentry.data) | {
                CONF_TARGET_ENTITY: _stored_target(self.hass, target),
                CONF_TARGET_ENTITY_ID: target,
            }
            title = f"{subentry.title.split(' ↔ ')[0]} ↔ {target}"
            return self.async_update_reload_and_abort(
                entry, subentry, data=data, title=title
            )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TARGET_ENTITY): EntitySelector(
                        EntitySelectorConfig()
                    ),
                }
            ),
        )


def _source_key_taken(entry: ConfigEntry, key_id: str) -> bool:
    """A physical key can drive only one link, across all link types."""
    return any(
        key_id
        in (
            subentry.data.get(CONF_SATELLITE_ID),
            subentry.data.get(CONF_TOGGLE_ID),
            subentry.data.get(CONF_KEY_ID),
            subentry.data.get(CONF_UP_KEY_ID),
            subentry.data.get(CONF_DOWN_KEY_ID),
        )
        for subentry in entry.subentries.values()
    )


# Backwards-compatible alias used by the satellite flows.
_satellite_taken = _source_key_taken


def _climate_source_options(hub) -> list[SelectOptionDict]:
    """Satellites and toggle keys, labeled by kind."""
    from .hub import ApplianceSwitch, SatelliteButton, Switch, ToggleLight

    options = []
    for device_id, device in hub.devices.items():
        if isinstance(device, SatelliteButton):
            options.append(
                SelectOptionDict(value=device_id, label=f"{device.name} (button)")
            )
        elif isinstance(device, (Switch, ToggleLight)) and not isinstance(
            device, ApplianceSwitch
        ):
            options.append(
                SelectOptionDict(value=device_id, label=f"{device.name} (toggle)")
            )
    return options


def _satellite_options(hub) -> list[SelectOptionDict]:
    from .hub import SatelliteButton

    return [
        SelectOptionDict(value=device_id, label=device.name)
        for device_id, device in hub.devices.items()
        if isinstance(device, SatelliteButton)
    ]


def _toggle_options(hub) -> list[SelectOptionDict]:
    from .hub import ApplianceSwitch, Switch, ToggleLight

    return [
        SelectOptionDict(value=device_id, label=device.name)
        for device_id, device in hub.devices.items()
        if isinstance(device, (Switch, ToggleLight))
        and not isinstance(device, ApplianceSwitch)
    ]
