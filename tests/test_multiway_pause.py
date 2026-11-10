"""Kill-switch: pausing Multiway must instantly detach every link.

multiway.py imports Home Assistant, which this suite runs without; a
minimal stub of the touched HA surface (config_entries, core, helpers)
lets the real LinkManager run against fake keys, states, and services.
The invariant proven here: while paused, NOTHING the integration hears
can produce a service call or a key write — including handler tasks
already in flight when the pause lands.
"""

import asyncio
import importlib
import sys
import types
from pathlib import Path

COMPONENT_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "vitrea"


def _install_ha_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = type("ConfigEntry", (), {})
    config_entries.ConfigSubentry = type("ConfigSubentry", (), {})

    core = types.ModuleType("homeassistant.core")

    class Context:
        def __init__(self, *args, **kwargs):
            pass

    core.Context = Context
    core.Event = type("Event", (), {})
    core.HomeAssistant = object
    core.callback = lambda func: func

    helpers = types.ModuleType("homeassistant.helpers")

    er = types.ModuleType("homeassistant.helpers.entity_registry")
    er.async_get = lambda hass: None
    er.async_validate_entity_id = lambda registry, stored: stored

    event_mod = types.ModuleType("homeassistant.helpers.event")

    def async_track_state_change_event(hass, entity_ids, handler):
        sub = (tuple(entity_ids), handler)
        hass.state_subs.append(sub)
        return lambda: hass.state_subs.remove(sub)

    def async_track_entity_registry_updated_event(hass, entity_id, handler):
        sub = (entity_id, handler)
        hass.registry_subs.append(sub)
        return lambda: hass.registry_subs.remove(sub)

    event_mod.async_track_state_change_event = async_track_state_change_event
    event_mod.async_track_entity_registry_updated_event = (
        async_track_entity_registry_updated_event
    )

    helpers.entity_registry = er
    ha.config_entries = config_entries
    ha.core = core
    ha.helpers = helpers

    sys.modules["homeassistant"] = ha
    sys.modules["homeassistant.config_entries"] = config_entries
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.entity_registry"] = er
    sys.modules["homeassistant.helpers.event"] = event_mod


def _import_multiway():
    _install_ha_stubs()
    if "custom_components.vitrea" not in sys.modules:
        pkg = types.ModuleType("custom_components")
        pkg.__path__ = [str(COMPONENT_DIR.parent)]
        vitrea_pkg = types.ModuleType("custom_components.vitrea")
        vitrea_pkg.__path__ = [str(COMPONENT_DIR)]
        sys.modules["custom_components"] = pkg
        sys.modules["custom_components.vitrea"] = vitrea_pkg
    return importlib.import_module("custom_components.vitrea.multiway")


# --- fakes ---


class FakeState:
    def __init__(self, state, attributes=None):
        self.state = state
        self.attributes = attributes or {}


class FakeStates:
    def __init__(self):
        self._states = {}

    def get(self, entity_id):
        return self._states.get(entity_id)

    def set(self, entity_id, state):
        self._states[entity_id] = FakeState(state)


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False, context=None):
        self.calls.append((domain, service, data.get("entity_id")))


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.services = FakeServices()
        self.state_subs = []
        self.registry_subs = []
        self.tasks = []

    def async_create_task(self, coro):
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.append(task)
        return task


class FakeSatellite:
    def __init__(self):
        self.event_callbacks = []
        self.indicator_value = False

    def register_event_callback(self, cb):
        self.event_callbacks.append(cb)

    def remove_event_callback(self, cb):
        self.event_callbacks.remove(cb)

    async def turn_on_indicator(self):
        self.indicator_value = True

    async def turn_off_indicator(self):
        self.indicator_value = False

    def press(self, event_type):
        for cb in list(self.event_callbacks):
            cb(event_type)


class FakeToggle:
    def __init__(self):
        self.callbacks = []
        self.is_on = False

    def register_callback(self, cb):
        self.callbacks.append(cb)

    def remove_callback(self, cb):
        self.callbacks.remove(cb)

    async def turn_on(self):
        self.is_on = True

    async def turn_off(self):
        self.is_on = False


class FakeController:
    def __init__(self):
        self.callbacks = []

    def register_callback(self, cb):
        self.callbacks.append(cb)

    def remove_callback(self, cb):
        self.callbacks.remove(cb)


class FakeHub:
    def __init__(self, devices):
        self.devices = devices
        self.supports_led_commands = False
        self.controller = FakeController()


class FakeSubentry:
    def __init__(self, subentry_type, subentry_id, title, data):
        self.subentry_type = subentry_type
        self.subentry_id = subentry_id
        self.title = title
        self.data = data


class FakeEntry:
    def __init__(self, subentries):
        self.subentries = subentries


async def _drain(hass):
    """Let created handler tasks run to completion."""
    for _ in range(5):
        await asyncio.sleep(0)


def _build():
    mw = _import_multiway()
    hass = FakeHass()
    hass.states.set("light.hall", "off")
    hass.states.set("switch.pump", "off")
    satellite = FakeSatellite()
    toggle = FakeToggle()
    hub = FakeHub({"sat1": satellite, "tog1": toggle})
    entry = FakeEntry(
        {
            "s1": FakeSubentry(
                "satellite_link",
                "s1",
                "Sat link",
                {"satellite_id": "sat1", "target_entity": "light.hall"},
            ),
            "t1": FakeSubentry(
                "toggle_link",
                "t1",
                "Tog link",
                {"toggle_id": "tog1", "target_entity": "switch.pump"},
            ),
        }
    )
    manager = mw.LinkManager(hass, entry, hub)
    return hass, hub, satellite, toggle, manager


async def test_setup_builds_links_and_subscriptions():
    hass, hub, satellite, toggle, manager = _build()
    await manager.async_setup()
    assert len(manager.links) == 2
    assert len(satellite.event_callbacks) == 1
    assert len(toggle.callbacks) == 1
    assert len(hub.controller.callbacks) == 1
    assert len(hass.state_subs) == 2
    await manager.async_teardown()
    await _drain(hass)


async def test_pause_detaches_everything():
    hass, hub, satellite, toggle, manager = _build()
    await manager.async_setup()
    await manager.async_set_enabled(False)
    await _drain(hass)

    assert manager.enabled is False
    assert manager.links == {}
    assert satellite.event_callbacks == []
    assert toggle.callbacks == []
    assert hub.controller.callbacks == []
    assert hass.state_subs == []
    # Nothing the wire produces can reach a service while paused.
    satellite.press("Short")
    await _drain(hass)
    assert hass.services.calls == []


async def test_pause_kills_in_flight_press():
    """A press whose handler task was already created must die on pause."""
    hass, hub, satellite, toggle, manager = _build()
    await manager.async_setup()
    satellite.press("Release")  # consumed as the poll artifact
    satellite.press("Short")  # handler task created, not yet run
    await manager.async_set_enabled(False)  # sets disabled before it runs
    await _drain(hass)
    assert hass.services.calls == []


async def test_resume_rebuilds_working_links():
    hass, hub, satellite, toggle, manager = _build()
    await manager.async_setup()
    await manager.async_set_enabled(False)
    await manager.async_set_enabled(True)
    await _drain(hass)

    assert len(manager.links) == 2
    assert len(hub.controller.callbacks) == 1
    satellite.press("Release")  # rebuilt link re-arms the poll baseline
    satellite.press("Short")
    await _drain(hass)
    assert hass.services.calls == [("homeassistant", "toggle", "light.hall")]
    await manager.async_teardown()
    await _drain(hass)


async def test_restore_paused_skips_link_build():
    """Kill-switch restored 'off' before setup: links must not be built."""
    hass, hub, satellite, toggle, manager = _build()
    manager.restore_paused()
    await manager.async_setup()
    assert manager.links == {}
    assert satellite.event_callbacks == []
    assert hub.controller.callbacks == []
    # A deliberate resume still works from the restored-paused state.
    await manager.async_set_enabled(True)
    assert len(manager.links) == 2
    await manager.async_teardown()
    await _drain(hass)


async def test_set_enabled_is_idempotent():
    hass, hub, satellite, toggle, manager = _build()
    await manager.async_setup()
    await manager.async_set_enabled(True)  # already enabled: no rebuild
    assert len(satellite.event_callbacks) == 1
    assert len(hub.controller.callbacks) == 1
    await manager.async_set_enabled(False)
    await manager.async_set_enabled(False)  # already paused: no-op
    assert manager.links == {}
    await _drain(hass)
