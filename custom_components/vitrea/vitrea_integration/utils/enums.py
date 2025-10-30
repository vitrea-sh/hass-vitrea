from enum import Enum

class KeyTypes(Enum):
    NotUsed = 0
    Toggle = 1
    PushButton = 2
    Dimmer = 3
    BlindUp = 4
    BlindDown = 5
    BlindUpAndDown = 6
    TiltUp = 7
    TiltDown = 8
    TiltUpAndDown = 9
    Boiler = 10
    Heater = 11
    Satellite = 12
    RoomOn = 13
    Scene = 14
    DND = 15
    Thermostat = 16
    UnderfloorHeating = 17
    Fan = 18
    ToggleMW = 19
    BlindMW = 20
    AC_TYPE_1 = 21
    AC_TYPE_2 = 22
    AC_TYPE_3 = 23
    AC_TYPE_TMSF = 24

class CommandNumber(Enum):
    GetFloorNumbers = 1
    GetFloorParams = 2
    GetRoomNumbers = 3
    GetRoomParams = 4
    GetKeypadNumbers = 5
    GetKeyParams = 6
    GetACNumbers = 7
    GetACParams = 8
    GetSceneNumbers = 9
    GetSceneParams = 10

class AirConditionerType(Enum):
    TYPE_1 = 1
    TYPE_2 = 2
    TYPE_3 = 3
    TMSF = 4

class ThermostatModes(Enum):
    COOL = 0
    HEAT = 1
    FAN = 2
    DRY = 3
    AUTO = 4
    NA = -1


class ThermostatFanSpeeds(Enum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    TOP = 3
    AUTO = 4
    NA = -1


class ThermostatTemperatureModes(Enum):
    CELSIUS = 0
    FAHRENHEIT = 1
    NA = -1

class DiscoveryMessages(Enum):
    MANAGER = "VITREA"
    HOST = "VITREA-HOST"
    APP = "VITREA-APP"
    VCLOUD = "VITREA-VCLOUD"