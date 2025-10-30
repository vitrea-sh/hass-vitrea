from typing import Any
from homeassistant.components.climate.const import ATTR_FAN_MODE, ATTR_HVAC_MODE
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_AUTO,
    HVACMode,
    UnitOfTemperature,
)
from .const import DOMAIN
from .hub import Climate
from .vitrea_integration.utils.enums import (
    ThermostatTemperatureModes,
    ThermostatFanSpeeds,
    ThermostatModes,
    AirConditionerType,
)
import logging
import asyncio

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        VitreaClimate(hvac) for hvac in hub.hvacs.values() if isinstance(hvac, Climate)
    )


class VitreaClimate(ClimateEntity):
    """Representation of a Vitrea Switch for Home Assistant."""

    _attr_should_poll = False

    FAN_SPEED_MAPPING = {
        ThermostatFanSpeeds.LOW.value: FAN_LOW,
        ThermostatFanSpeeds.MEDIUM.value: FAN_MEDIUM,
        ThermostatFanSpeeds.HIGH.value: FAN_HIGH,
        ThermostatFanSpeeds.AUTO.value: FAN_AUTO,
    }
    HVAC_MODES_MAPPING = {
        ThermostatModes.HEAT.value: HVACMode.HEAT,
        ThermostatModes.COOL.value: HVACMode.COOL,
        ThermostatModes.FAN.value: HVACMode.FAN_ONLY,
        ThermostatModes.AUTO.value: HVACMode.AUTO,
    }
    TEMPERATURE_UNITS_MAPPING = {
        ThermostatTemperatureModes.CELSIUS.value: UnitOfTemperature.CELSIUS,
        ThermostatTemperatureModes.FAHRENHEIT.value: UnitOfTemperature.FAHRENHEIT,
    }

    def __init__(self, thermostat: Climate):
        """Initialize the switch."""
        self._thermostat = thermostat
        self._attr_name = thermostat.name
        self._attr_unique_id = f"{thermostat.hub.hub_id}-{thermostat.node_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": thermostat.name,
            "manufacturer": "Vitrea",
            "model": "TMSF"
            if thermostat.thermostat_type.value == AirConditionerType.TMSF.value
            else "TMST",
        }
        self._attr_precision = 1.0

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._thermostat.hub.online

    @property
    def supported_features(self) -> list[ClimateEntityFeature]:
        """Return the list of supported features."""
        if self._thermostat.thermostat_type == AirConditionerType.TMSF:
            return (
                ClimateEntityFeature.TARGET_TEMPERATURE
                | ClimateEntityFeature.TURN_ON
                | ClimateEntityFeature.TURN_OFF
            )
        return (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.FAN_MODE
        )

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        if not self._thermostat.temperature_mode:
            return UnitOfTemperature.CELSIUS
        return self.TEMPERATURE_UNITS_MAPPING[self._thermostat.temperature_mode.value]

    @property
    def hvac_modes(self) -> list[str]:
        """Return the list of available operation modes."""
        if self._thermostat.thermostat_type == AirConditionerType.TMSF:
            variant_supported_modes = [HVACMode.HEAT]
        else:
            variant_supported_modes = [
                self.HVAC_MODES_MAPPING[mode.value]
                for mode in self._thermostat.supported_operation_modes
            ]
        supported_modes = [*variant_supported_modes, HVACMode.OFF]
        return supported_modes

    @property
    def fan_modes(self) -> list[str]:
        """Return the list of available fan modes."""
        if not self._thermostat.supported_fan_speeds:
            return None
        return [
            self.FAN_SPEED_MAPPING[speed.value]
            for speed in self._thermostat.supported_fan_speeds
        ]

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._thermostat.measured_temperature

    @property
    def target_temperature(self) -> float:
        """Return the temperature we try to reach."""
        return self._thermostat.set_temperature

    @property
    def hvac_mode(self) -> str:
        """Return current operation ie. heat, cool, idle."""
        if not self._thermostat.state:
            return HVACMode.OFF
        elif self._thermostat.thermostat_type == AirConditionerType.TMSF:
            return HVACMode.HEAT
        return self.HVAC_MODES_MAPPING[self._thermostat.operation_mode.value]

    @property
    def fan_mode(self) -> str:
        """Return the current fan mode."""
        if not self._thermostat.fan_speed:
            return None
        return self.FAN_SPEED_MAPPING.get(self._thermostat.fan_speed.value, None)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return float(self._thermostat.temperature_range[0])

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return float(self._thermostat.temperature_range[1])

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method, so to this we add the 'self.async_write_ha_state' method, to be
        # called where ever there are changes.
        # The call back registration is done once this entity is registered with HA
        # (rather than in the __init__)
        self._thermostat.register_callback(self.schedule_update_ha_state)

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        await self._thermostat.turn_on()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        await self._thermostat.turn_off()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        await self._thermostat.turn_on(temperature=temperature)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode, **kwargs: Any) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self._thermostat.turn_off()
            return
        if not self._thermostat.state:
            await self._thermostat.turn_on()
            await asyncio.sleep(0.05)
        if (
            self._thermostat.thermostat_type == AirConditionerType.TMSF
            and hvac_mode == HVACMode.HEAT
        ):
            await self._thermostat.turn_on()
            return
        mode = next(
            mode
            for mode, value in self.HVAC_MODES_MAPPING.items()
            if value == hvac_mode
        )
        mode = ThermostatModes(mode)
        await self._thermostat.turn_on(mode=mode)

    async def async_set_fan_mode(self, fan_mode) -> None:
        """Set new target fan mode."""
        speed = next(
            speed
            for speed, value in self.FAN_SPEED_MAPPING.items()
            if value == fan_mode
        )
        speed = ThermostatFanSpeeds(speed)
        await self._thermostat.turn_on(fan_speed=speed)
