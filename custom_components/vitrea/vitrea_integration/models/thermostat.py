from typing import Union
from ..control_api.commands import (
    GetThermostatStatusCommand,
    ThermostatOnCommand,
    ThermostatOffCommand,
    ThermostatSetParamsCommand,
    ThermostatParams,
    ThermostatCommandTypes,
    ThermostatUpCommand,
    ThermostatDownCommand,
)
from ..vbox_controller import VBoxController
from ..utils.enums import (
    ThermostatFanSpeeds,
    ThermostatModes,
    AirConditionerType,
    ThermostatTemperatureModes,
)

from .base import BaseDevice
from enum import Enum

# Validate Duration, supported key types and state
import logging

_LOGGER = logging.getLogger(__name__)


TYPE_1_FAN_SPEEDS = (
    ThermostatFanSpeeds.LOW,
    ThermostatFanSpeeds.MEDIUM,
    ThermostatFanSpeeds.HIGH,
)
TYPE_2_FAN_SPEEDS = (
    ThermostatFanSpeeds.LOW,
    ThermostatFanSpeeds.MEDIUM,
    ThermostatFanSpeeds.HIGH,
    ThermostatFanSpeeds.AUTO,
)
TYPE_3_FAN_SPEEDS = ()
TYPE_TMSF_FAN_SPEEDS = ()

TYPE_1_OPERATION_MODES = (
    ThermostatModes.COOL,
    ThermostatModes.HEAT,
    ThermostatModes.FAN,
)
TYPE_2_OPERATION_MODES = (
    ThermostatModes.COOL,
    ThermostatModes.HEAT,
    ThermostatModes.FAN,
)
TYPE_3_OPERATION_MODES = (
    ThermostatModes.COOL,
    ThermostatModes.HEAT,
    ThermostatModes.FAN,
    ThermostatModes.AUTO,
)
TYPE_TMSF_OPERATION_MODES = ()


class Thermostat(BaseDevice):
    supported_key_types = []

    def __init__(
        self,
        node_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        thermostat_type: AirConditionerType,
        initial_state: bool = False,
        **kwargs,
    ):
        super().__init__(
            node_id=node_id,
            key_name=key_name,
            room_name=room_name,
            controller=controller,
            **kwargs,
        )
        self.thermostat_type = thermostat_type
        self._state = initial_state
        self.temperature_mode = None
        self.set_temperature = None
        self.fan_speed = None
        self.operation_mode = None
        self.measured_temperature = None
        if thermostat_type == AirConditionerType.TMSF:
            self.relay_state = None

    @property
    def state(self) -> bool:
        return self._state

    @property
    def operation_parameters(self) -> dict:
        return ThermostatParams(
            mode=self.operation_mode,
            fan_speed=self.fan_speed,
            temperature_mode=self.temperature_mode,
            temperature=self.set_temperature,
        )

    @property
    def supported_fan_speeds(self) -> Enum:
        match self.thermostat_type.value: # WHY VALUE?
            case AirConditionerType.TYPE_1.value:
                return TYPE_1_FAN_SPEEDS
            case AirConditionerType.TYPE_2.value:
                return TYPE_2_FAN_SPEEDS
            case AirConditionerType.TYPE_3.value:
                return TYPE_3_FAN_SPEEDS
            case AirConditionerType.TMSF.value:
                return TYPE_TMSF_FAN_SPEEDS
            case _:
                return None

    @property
    def supported_operation_modes(self) -> list:
        match self.thermostat_type.value:
            case AirConditionerType.TYPE_1.value:
                return TYPE_1_OPERATION_MODES
            case AirConditionerType.TYPE_2.value:
                return TYPE_2_OPERATION_MODES
            case AirConditionerType.TYPE_3.value:
                return TYPE_3_OPERATION_MODES
            case AirConditionerType.TMSF.value:
                return TYPE_TMSF_OPERATION_MODES
            case _:
                return None

    @property
    def temperature_range(self) -> tuple:
        if self.temperature_mode:
            if self.temperature_mode.value == ThermostatTemperatureModes.CELSIUS.value:
                return (15, 30)
            elif (
                self.temperature_mode.value
                == ThermostatTemperatureModes.FAHRENHEIT.value
            ):
                return (60, 90)
        return (15, 90)

    async def _turn_on(self) -> bool:
        if self.operation_mode and self.fan_speed and self.temperature_mode and self.set_temperature:
            params = ThermostatParams(
                full_command=True,
                mode=self.operation_mode,
                fan_speed=self.fan_speed,
                temperature_mode=self.temperature_mode,
                temperature=self.set_temperature,
            )
            await self.controller.connection.send(
                ThermostatSetParamsCommand(node_id=self.node_id, params=params).serialize()
            )
        else:
            await self.controller.connection.send(
                ThermostatOnCommand(node_id=self.node_id).serialize()
            )
        return True

    async def turn_on(
        self,
        mode: Union[ThermostatModes, None] = None,
        fan_speed: Union[ThermostatFanSpeeds, None] = None,
        temperature_mode: Union[ThermostatTemperatureModes, None] = None,
        temperature: Union[int, None] = None,
    ) -> bool:
        # full command is needed if number of params with values is more than 1
        params_count_with_values = 4 - [
            mode,
            fan_speed,
            temperature_mode,
            temperature,
        ].count(None)
        if params_count_with_values == 0:
            return await self._turn_on()
        elif params_count_with_values == 1:
            if mode:
                mode = ThermostatModes(mode.value)
                params = ThermostatParams(full_command=False, mode=mode)
            elif fan_speed:
                fan_speed = ThermostatFanSpeeds(fan_speed.value)
                params = ThermostatParams(full_command=False, fan_speed=fan_speed)
            elif temperature_mode:
                temperature_mode = ThermostatTemperatureModes(temperature_mode.value)
                params = ThermostatParams(
                    full_command=False, temperature_mode=temperature_mode
                )
            elif temperature:
                params = ThermostatParams(full_command=False, temperature=temperature)
        elif params_count_with_values > 1:
            params = ThermostatParams(
                full_command=True,
                mode=mode if mode else self.operation_mode,
                fan_speed=fan_speed if fan_speed else self.fan_speed,
                temperature_mode=temperature_mode
                if temperature_mode
                else self.temperature_mode,
                temperature=temperature if temperature else self.set_temperature,
            )
        if not params:
            return False
        await self.controller.connection.send(
            ThermostatSetParamsCommand(node_id=self.node_id, params=params).serialize()
        )
        return True

    async def turn_off(self) -> bool:
        await self.controller.connection.send(
            ThermostatOffCommand(node_id=self.node_id).serialize()
        )
        return True
    
    async def temperature_up(self) -> bool:
        await self.controller.connection.send(
            ThermostatUpCommand(node_id=self.node_id).serialize()
        )
        return True
    
    async def temperature_down(self) -> bool:
        await self.controller.connection.send(
            ThermostatDownCommand(node_id=self.node_id).serialize()
        )
        return True

    async def get_state(self):
        await self.controller.connection.send(
            GetThermostatStatusCommand(node_id=self.node_id).serialize()
        )
        return True

    @property
    def is_on(self) -> bool:
        """Return the state of the switch."""
        return self._state

    @is_on.setter
    def is_on(self, value: bool):
        self._state = value

    async def update_state(self, data):
        """Update the state of the switch."""
        self.is_on = data.get("status")
        params = data.get("parameters", {})
        self.operation_mode = params.get("mode")
        self.fan_speed = params.get("fan_speed")
        self.set_temperature = params.get("set_temperature")
        self.measured_temperature = params.get("measured_temperature")
        self.temperature_mode = params.get("temperature_mode")
        if self.thermostat_type == AirConditionerType.TMSF:
            self.relay_state = params.get("relay_state")
        await self.publish_updates()
