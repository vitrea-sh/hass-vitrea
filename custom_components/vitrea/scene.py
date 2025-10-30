from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from .const import DOMAIN
from .hub import Scene as HubScene
import voluptuous as vol


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: entity_platform.AddEntitiesCallback,
):
    """Set up Vitrea switches."""
    hub = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities(
        VitreaScene(scene)
        for scene in hub.scenes.values()
        if isinstance(scene, HubScene)
    )


class VitreaScene(Scene):
    """Representation of a Vitrea Scene for Home Assistant."""

    def __init__(self, scene: HubScene):
        """Initialize the scene."""
        self._scene = scene
        self._attr_name = scene.name
        self._attr_unique_id = f"{scene.hub.hub_id}-{scene.scene_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, self._attr_unique_id)},
            "name": scene.name,
            "manufacturer": "Vitrea",
            "model": "Vitrea Scenario",
        }

    @property
    def available(self) -> bool:
        """Return True if switch and hub is available."""
        return self._scene.hub.online

    async def async_added_to_hass(self) -> None:
        """Run when this Entity has been added to HA."""
        # Importantly for a push integration, the module that will be getting updates
        # needs to notify HA of changes. The dummy device has a registercallback
        # method that will be called when the device is updated.
        self._scene.register_callback(self.schedule_update_ha_state)

    async def async_activate(self, **kwargs):
        """Turn the scene on."""
        await self._scene.run()
