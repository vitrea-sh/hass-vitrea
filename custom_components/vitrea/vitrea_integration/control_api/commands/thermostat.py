from enum import Enum
from .base import Command
from typing import Union
from ...utils.enums import (
    ThermostatFanSpeeds,
    ThermostatModes,
    ThermostatTemperatureModes,
)
import logging

_LOGGER = logging.getLogger(__name__)


class ThermostatCommandTypes(Enum):
    FULL_COMMAND = 1
    CHANGE_STATE = 2
    CHANGE_OPERATION_MODE = 3
    CHANGE_FAN_SPEED = 4
    SET_TEMPERATURE = 5
    RAISE_TEMPERATURE = 6
    LOWER_TEMPERATURE = 7
    CHANGE_TEMPERATURE_MODE = 8


class ThermostatParams:
    def __init__(
        self,
        full_command=False,
        mode: Union[ThermostatModes, None] = None,
        fan_speed: Union[ThermostatFanSpeeds, None] = None,
        temperature_mode: Union[ThermostatTemperatureModes, None] = None,
        temperature: Union[int, None] = None,
    ):
        self.mode = mode
        self.fan_speed = fan_speed
        self.temperature_mode = temperature_mode
        self.temperature = temperature
        self.full_command = full_command

    def validate(self, full_command: bool):
        self._validate_input_attributes()
        if full_command:
            self._validate_full_command()
        else:
            self._validate_partial_command()

    def _validate_input_attributes(self):
        if self.mode is not None and not isinstance(self.mode, ThermostatModes):
            raise ValueError("Mode must be of type ThermostatModes.")
        if self.fan_speed is not None and not isinstance(
            self.fan_speed, ThermostatFanSpeeds
        ):
            raise ValueError("Fan speed must be of type ThermostatFanSpeeds.")
        if self.temperature_mode is not None and not isinstance(
            self.temperature_mode, ThermostatTemperatureModes
        ):
            raise ValueError(
                "Temperature mode must be of type ThermostatTemperatureModes."
            )
        if self.temperature is not None and not isinstance(self.temperature, int):
            try:
                self.temperature = int(self.temperature)
            except ValueError as e:
                raise ValueError("Temperature must be of type int.") from e

    def _validate_full_command(self):
        if self.mode is None:
            raise ValueError("Mode must be set for full command.")
        if self.fan_speed is None:
            raise ValueError("Fan speed must be set for full command.")
        if self.temperature_mode is None:
            raise ValueError("Temperature mode must be set for full command.")
        if self.temperature is None:
            raise ValueError("Temperature must be set for full command.")

    def _validate_partial_command(self):
        is_param_with_value = False
        for param in [
            self.mode,
            self.fan_speed,
            self.temperature_mode,
            self.temperature,
        ]:
            if param is not None:
                if is_param_with_value:
                    raise ValueError("Only one parameter can be set.")
                is_param_with_value = True

    def get_command_type(self):
        if self.mode is not None:
            return ThermostatCommandTypes.CHANGE_OPERATION_MODE
        if self.fan_speed is not None:
            return ThermostatCommandTypes.CHANGE_FAN_SPEED
        if self.temperature_mode is not None:
            return ThermostatCommandTypes.CHANGE_TEMPERATURE_MODE
        if self.temperature is not None:
            return ThermostatCommandTypes.SET_TEMPERATURE
        raise ValueError("No parameter set.")

    def serialize(self):
        self.validate(self.full_command)
        command_type = (
            ThermostatCommandTypes.FULL_COMMAND
            if self.full_command
            else self.get_command_type()
        )
        result = f"{command_type.value}:"
        match command_type:
            case ThermostatCommandTypes.FULL_COMMAND:
                result += f"O:{self.mode.value}{self.fan_speed.value}:{self.temperature:03d}:{self.temperature_mode.value}"
            case ThermostatCommandTypes.CHANGE_OPERATION_MODE:
                result += f"{self.mode.value}"
            case ThermostatCommandTypes.CHANGE_FAN_SPEED:
                result += f"{self.fan_speed.value}"
            case ThermostatCommandTypes.SET_TEMPERATURE:
                result += f"{self.temperature:03d}"
            case ThermostatCommandTypes.CHANGE_TEMPERATURE_MODE:
                result += f"{self.temperature_mode.value}"
            case _:
                raise ValueError("Invalid command type.")
        return result


class ThermostatOnCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:2:O\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")

    # TODO - adjust to splitting TMSF and TMST According to Types


class ThermostatOffCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:2:F\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")


class ThermostatSetParamsCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:{param_object}\r\n"

    def __init__(self, node_id, params: ThermostatParams):
        self.node_id = node_id
        self.params = params

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id, param_object=self.params.serialize()
        ).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.param, ThermostatParams):
            raise ValueError("Param must be an instance of ThermostatParam.")


class ThermostatUpCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:6\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")


class ThermostatDownCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:7\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
