"""Config flow for Vitrea integration."""

import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .vitrea_integration import validate_controller_availability

_LOGGER = logging.getLogger(__name__)


class VitreaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Vitrea Config Flow."""

    VERSION = 1
    MINOR_VERSION = 1
    STEP_USER_DATA_SCHEMA = vol.Schema(
        {
            vol.Required("ip", default="192.168.1.136"): str,
            vol.Required("port", default=11502): int,
            vol.Required("append_room_to_name", default=True): bool,
            vol.Required("filter_mw", default=True): bool,
        }
    )

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle a flow initialized by the user."""
        if user_input is not None:
            # Check first if not already configured
            await self.async_set_unique_id(user_input.get("ip"))
            self._abort_if_unique_id_configured()
            result = await validate_controller_availability(
                user_input.get("ip"), user_input.get("port")
            )
            _LOGGER.debug(result)
            if not result.get("supported", False):
                return self.async_abort(
                    reason=result.get("reason"),
                    description_placeholders=result,
                )
            return self.async_create_entry(
                title="Vitrea Gateway",
                data={
                    **user_input,
                    "supports_led_commands": result.get("supports_led_commands", False),
                },
            )
        return self.async_show_form(
            step_id="user", data_schema=self.STEP_USER_DATA_SCHEMA
        )
