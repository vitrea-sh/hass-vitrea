"""Vitrea Hub class."""

import logging
from numbers import Number

from .vitrea_integration.models.thermostat import (
    Thermostat,
)
from homeassistant.core import HomeAssistant

from .vitrea_integration import VBoxController
from .vitrea_integration.models.blind import Blind
from .vitrea_integration.models.light import Dimmer
from .vitrea_integration.models.toggle import Toggle
from .vitrea_integration.models.satellite import Satellite
from .vitrea_integration.models.push_button import PushButton as PushButtonModel
from .vitrea_integration.models.scenario import Scenario
from .vitrea_integration.utils.enums import (
    AirConditionerType,
    KeyTypes as VitreaKeyTypes,
)

_LOGGER = logging.getLogger(__name__)


class Switch(Toggle):
    """Representation of a Vitrea Switch."""

    SUPPORTS_TIMER = True

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Switch."""
        super().__init__(
            node_id=node_id,
            key_id=key_id,
            key_name=key_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub


class Light(Dimmer):
    """Representation of a Vitrea Light."""

    SUPPORTS_TIMER = True

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Light."""
        super().__init__(
            node_id=node_id,
            key_id=key_id,
            key_name=key_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub


class Cover(Blind):
    """Representation of a Vitrea Cover."""

    SUPPORTS_TIMER = True

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Cover."""
        super().__init__(
            node_id=node_id,
            key_id=key_id,
            key_name=key_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub

    @property
    def current_cover_position(self) -> int:
        """Return the current position of the cover."""
        return self.location


class SatelliteButton(Satellite):
    """Representation of a Vitrea Satellite Button."""

    SUPPORTS_TIMER = False

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Satellite Button."""
        super().__init__(
            node_id=node_id,
            key_id=key_id,
            key_name=key_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub


class PushButton(PushButtonModel):
    """Representation of a Vitrea Push Button."""

    SUPPORTS_TIMER = False

    def __init__(
        self,
        node_id: int,
        key_id: int,
        key_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Push Button."""
        super().__init__(
            node_id=node_id,
            key_id=key_id,
            key_name=key_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub


class Scene(Scenario):
    """Representation of a Vitrea Scene."""

    SUPPORTS_TIMER = False

    def __init__(
        self,
        scene_id: int,
        scene_name: str,
        room_name: str,
        hub: "VitreaHub",
        **kwargs,
    ):
        """Initialize the Vitrea Scene."""
        super().__init__(
            scene_id=scene_id,
            scene_name=scene_name,
            room_name=room_name,
            controller=hub.controller,
            **kwargs,
        )
        self.hub = hub


class Climate(Thermostat):
    """Representation of a Vitrea Climate."""

    def __init__(
        self,
        node_id: int,
        key_name: str,
        room_name: str,
        controller: VBoxController,
        thermostat_type: AirConditionerType,
        hub: "VitreaHub",
        initial_state: bool = False,
        **kwargs,
    ):
        """Initialize the Vitrea Climate."""
        super().__init__(
            node_id=node_id,
            key_name=key_name,
            room_name=room_name,
            controller=controller,
            thermostat_type=thermostat_type,
            initial_state=initial_state,
            **kwargs,
        )
        self.hub = hub


class VitreaHub:
    """Vitrea Hub class."""

    manufacturer = "Vitrea"
    supported_classes = [Light, Switch, Cover, SatelliteButton, PushButton]
    MW_KEY_TYPES = [VitreaKeyTypes.BlindMW.value, VitreaKeyTypes.ToggleMW.value]

    def __init__(
        self,
        host: str,
        port: int,
        hass: HomeAssistant,
        append_room_name: bool = True,
        supports_led_commands: bool = False,
    ) -> None:
        """Initialize the Vitrea Hub."""
        self.host = host
        self.port = port
        self.hass = hass
        self._id = host
        self.online = False
        self.append_room_name = append_room_name
        self.devices = {}
        self.scenes = {}
        self.hvacs = {}
        self.controller = VBoxController(
            ip=host, port=port, status_update_callback=self.update_state_callback
        )
        self.supports_led_commands = supports_led_commands

    async def read_gateway(self, filter_mw: bool = True):
        """Initialize the Vitrea Hub."""
        self.online = await self.controller.connect()
        if not self.online:
            reason = "Failed to connect to Vitrea Gateway"
            _LOGGER.error(reason)
            return False, reason
        await self._get_devices(filter_mw)
        if not self.devices:
            reason = "Failed to get devices from Vitrea Gateway"
            _LOGGER.error(reason)
            return False, reason
        return True, ""

    async def _get_devices(self, filter_mw: bool):
        """Get devices from Vitrea."""
        _LOGGER.debug("Fetching Vitrea devices")
        data = self.controller.database.serialize()
        for key in data.get("keys", []):
            if filter_mw and (
                "MW" in key.get("name", "")
                or key.get("type", {}).get("value", 0) in self.MW_KEY_TYPES
            ):
                continue
            for device_cls in self.supported_classes:
                key_type = key.get("type", {}).get("value", 0)
                if key_type in device_cls.supported_key_types:
                    device = device_cls(
                        node_id=key.get("keypad_id"),
                        key_id=key.get("id"),
                        key_name=key.get("name"),
                        room_name=key.get("room", {}).get("name", ""),
                        hub=self,
                        append_room_to_name=self.append_room_name,
                        add_timer=key_type == VitreaKeyTypes.Boiler.value,
                    )
                    self.devices[device._id] = device
                    await device.get_state()
        for scenario in data.get("scenarios", []):
            room = scenario.get("room", None)
            if not room:
                room = {}
            scenario = Scene(
                scene_id=scenario.get("id"),
                scene_name=scenario.get("name"),
                room_name=room.get("name", ""),
                hub=self,
                append_room_to_name=self.append_room_name,
            )
            self.scenes[scenario._id] = scenario
        for hvac in data.get("air_conditioners", []):
            room = hvac.get("room", None)
            if not room:
                room = {}
            tmst_type = AirConditionerType(hvac.get("type").get("value", 99))
            tmst = Climate(
                node_id=hvac.get("id"),
                key_name=hvac.get("name"),
                room_name=room.get("name", ""),
                thermostat_type=tmst_type,
                controller=self.controller,
                hub=self,
                initial_state=False,
                append_room_to_name=self.append_room_name,
            )
            self.hvacs[tmst._id] = tmst
            await tmst.get_state()

    @property
    def hub_id(self) -> str:
        """Return the ID of this Vitrea Hub."""
        return self._id

    async def test_connection(self):
        """Test the connection to the Vitrea Hub."""
        return self.controller.connection.connected

    async def update_state_callback(self, result):
        """Update the state of a device."""
        if result.get("type") == "node_status":
            node = f"N{result.get('node_id'):03d}-{result.get('key')}"
            device = self.devices.get(node, None)
            if device:
                await device.update_state(result)
        elif result.get("type") == "connection":
            self.online = result.get("status")
            for device in self.devices.values():
                await device.publish_updates()
            for scene in self.scenes.values():
                await scene.publish_updates()
            for hvac in self.hvacs.values():
                await hvac.publish_updates()
        elif result.get("type") == "ac_status":
            hvac = self.hvacs.get(f"N{result.get('ac_id'):03d}", None)
            if hvac:
                await hvac.update_state(result)

    async def async_unload_entry(self):
        """Disconnect from the Vitrea Hub."""
        await self.controller.close()
        return True
