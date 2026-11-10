"""Multiway links: bind physical Vitrea keys to arbitrary HA entities.

Two link types, one subentry each:
- Satellite link: Short press toggles the target entity, optional Long
  press scene; the button LED follows the target's on/off state
  (firmware 9.5+). Inherently loop-free (events in, LED writes out).
- Toggle link: a regular toggle key kept bidirectionally in sync with
  the target entity. Loop safety is delegated to ToggleLinkCore
  (echo suppression + idempotence + circuit breaker), which is fully
  unit-tested in tests/test_multiway_core.py.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
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
    SUBENTRY_TYPE_BLIND_LINK,
    SUBENTRY_TYPE_CLIMATE_LINK,
    SUBENTRY_TYPE_SATELLITE_LIGHT_LINK,
    SUBENTRY_TYPE_SATELLITE_LINK,
    SUBENTRY_TYPE_TOGGLE_LINK,
)
from .multiway_core import (
    BREAKER_OPEN,
    SYNC_ENTITY,
    SYNC_KEY,
    UNAVAILABLE_STATES,
    BlindMotionTracker,
    DimmerSweep,
    ToggleLinkCore,
    blind_led_states,
    blind_long_press_action,
    blind_short_press_action,
    choose_dim_direction,
    climate_short_press_action,
)

_LOGGER = logging.getLogger(__name__)

# Give the post-reconnect NALL:G sync a moment to refresh key states
# before links re-seed themselves.
RESYNC_DELAY = 3.0


def _resolve_target(hass: HomeAssistant, stored: str) -> str | None:
    """Resolve a stored registry UUID (or legacy entity_id) to an entity_id."""
    try:
        return er.async_validate_entity_id(er.async_get(hass), stored)
    except Exception:  # noqa: BLE001 - unknown/removed registry entry
        return None


def _state_to_bool(state: str | None) -> bool | None:
    if state == "on":
        return True
    if state == "off":
        return False
    return None


class _BaseLink:
    """Shared plumbing: target resolution, rename tracking, teardown."""

    def __init__(self, hass: HomeAssistant, hub, subentry: ConfigSubentry) -> None:
        self.hass = hass
        self.hub = hub
        self.subentry = subentry
        self.target_entity_id: str | None = _resolve_target(
            hass, subentry.data[CONF_TARGET_ENTITY]
        )
        if self.target_entity_id is None:
            # Registry UUID gone (integration was removed and re-added):
            # fall back to the entity_id captured at link creation, if it
            # exists again.
            fallback = subentry.data.get(CONF_TARGET_ENTITY_ID)
            if fallback and hass.states.get(fallback) is not None:
                self.target_entity_id = fallback
        self._unsubs: list = []
        self._unsub_state = None
        self.disabled = False

    def _track_target(self, state_handler) -> bool:
        """Subscribe to target state + registry changes. False if unresolvable."""
        if self.target_entity_id is None:
            _LOGGER.warning(
                "Multiway link '%s': target entity not found; link disabled",
                self.subentry.title,
            )
            self.disabled = True
            return False
        self._state_handler = state_handler
        self._unsub_state = async_track_state_change_event(
            self.hass, [self.target_entity_id], state_handler
        )
        self._unsubs.append(
            async_track_entity_registry_updated_event(
                self.hass, self.target_entity_id, self._on_registry_update
            )
        )
        return True

    async def _on_registry_update(self, event: Event) -> None:
        action = event.data.get("action")
        if action == "remove":
            _LOGGER.warning(
                "Multiway link '%s': target entity was removed; link disabled",
                self.subentry.title,
            )
            self.disabled = True
            if self._unsub_state:
                self._unsub_state()
                self._unsub_state = None
        elif action == "update" and "old_entity_id" in event.data:
            new_entity_id = event.data["entity_id"]
            _LOGGER.info(
                "Multiway link '%s': target renamed to %s",
                self.subentry.title,
                new_entity_id,
            )
            self.target_entity_id = new_entity_id
            if self._unsub_state:
                self._unsub_state()
            self._unsub_state = async_track_state_change_event(
                self.hass, [new_entity_id], self._state_handler
            )

    async def _call_service(
        self, domain: str, service: str, entity_id: str, **data
    ) -> bool:
        try:
            await self.hass.services.async_call(
                domain,
                service,
                {"entity_id": entity_id, **data},
                blocking=True,
                context=Context(),
            )
            return True
        except Exception as err:  # noqa: BLE001 - target may reject the call
            _LOGGER.warning(
                "Multiway link '%s': %s.%s on %s failed: %s",
                self.subentry.title,
                domain,
                service,
                entity_id,
                err,
            )
            return False

    @callback
    def on_connection_event(self) -> None:
        """Connection changed: prepare to absorb the next poll baseline."""

    def _base_teardown(self) -> None:
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()


class SatelliteLink(_BaseLink):
    """Short press toggles the target; LED follows the target's state."""

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.satellite = hub.devices.get(subentry.data.get(CONF_SATELLITE_ID))
        self.long_press_scene: str | None = subentry.data.get(CONF_LONG_PRESS_SCENE)
        # The status poll after (re)connect reports each satellite's stored
        # state once; that first event is a poll artifact, not a press.
        self._suppress_first_event = True

    async def async_setup(self) -> bool:
        if self.satellite is None:
            _LOGGER.warning(
                "Multiway link '%s': satellite key not found; link disabled",
                self.subentry.title,
            )
            self.disabled = True
            return False
        if not self._track_target(self._on_target_state):
            return False
        self.satellite.register_event_callback(self._on_button_event)
        await self.resync()
        _LOGGER.debug("Satellite link ready: %s", self.subentry.title)
        return True

    async def async_teardown(self) -> None:
        if self.satellite is not None:
            self.satellite.remove_event_callback(self._on_button_event)
        self._base_teardown()

    @callback
    def on_connection_event(self) -> None:
        self._suppress_first_event = True

    @callback
    def _consume_poll_artifact(self, event_type: str) -> bool:
        """The first event after a (re)connect is the status poll reporting
        the key's stored state — never a real press."""
        if not self._suppress_first_event:
            return False
        self._suppress_first_event = False
        if event_type != "Release":
            _LOGGER.debug(
                "Multiway '%s': ignoring first %s after sync (poll artifact)",
                self.subentry.title,
                event_type,
            )
        return True

    def _target_is_on(self, state: str | None) -> bool | None:
        """Interpret the target's state for LED feedback."""
        return _state_to_bool(state)

    def _observe_target(self, state: str | None) -> None:
        """Hook: subclasses learn from every target state report."""

    @callback
    def _on_button_event(self, event_type: str) -> None:
        if self.disabled:
            return
        if self._consume_poll_artifact(event_type):
            return
        if event_type == "Short":
            self.hass.async_create_task(self._handle_short_press())
        elif event_type == "Long" and self.long_press_scene:
            self.hass.async_create_task(
                self._call_service("scene", "turn_on", self.long_press_scene)
            )

    async def _handle_short_press(self) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        _LOGGER.info(
            "Multiway '%s': short press -> toggling %s",
            self.subentry.title,
            self.target_entity_id,
        )
        await self._call_service("homeassistant", "toggle", self.target_entity_id)

    async def _on_target_state(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        state_str = new_state.state if new_state else None
        self._observe_target(state_str)
        await self._apply_led(self._target_is_on(state_str))

    async def _apply_led(self, is_on: bool | None) -> None:
        """Mirror the target state onto the button LED (deduplicated)."""
        if is_on is None or self.disabled or not self.hub.supports_led_commands:
            return
        if self.satellite.indicator_value == is_on:
            return
        if is_on:
            await self.satellite.turn_on_indicator()
        else:
            await self.satellite.turn_off_indicator()

    async def resync(self) -> None:
        """Seed/re-seed the LED from the target's current state."""
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        state_str = state.state if state else None
        self._observe_target(state_str)
        await self._apply_led(self._target_is_on(state_str))


class SatelliteLightLink(SatelliteLink):
    """Short press toggles a light; holding the button dims it.

    The sweep sends absolute brightness percentages from a virtual
    position (never relative steps), so slow lights cannot lag the loop
    into compounding errors and dimming down can never switch the light
    off. The sweep is finite by construction — even a lost Release stops
    at the configured bound.
    """

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.long_press_scene = None  # long press is the dimming loop
        data = subentry.data
        self._min_pct = int(data.get(CONF_MIN_BRIGHTNESS, 1))
        self._max_pct = int(data.get(CONF_MAX_BRIGHTNESS, 100))
        self._step_pct = int(data.get(CONF_STEP_PCT, 5))
        self._step_delay = int(data.get(CONF_STEP_DELAY, 300)) / 1000
        self._dim_task: asyncio.Task | None = None
        self._last_up: bool | None = None

    @callback
    def _on_button_event(self, event_type: str) -> None:
        if self.disabled:
            return
        if self._consume_poll_artifact(event_type):
            return
        if event_type == "Short":
            self.hass.async_create_task(self._handle_short_press())
        elif event_type == "Long":
            self._start_dimming()
        elif event_type == "Release":
            self._stop_dimming()

    @callback
    def _start_dimming(self) -> None:
        self._stop_dimming()
        self._dim_task = self.hass.async_create_task(self._dim_loop())

    @callback
    def _stop_dimming(self) -> None:
        if self._dim_task and not self._dim_task.done():
            self._dim_task.cancel()
        self._dim_task = None

    async def _dim_loop(self) -> None:
        try:
            if self.target_entity_id is None:
                return
            state = self.hass.states.get(self.target_entity_id)
            light_on = state is not None and state.state == "on"
            brightness = state.attributes.get("brightness") if state else None
            brightness_pct = (
                round(brightness / 255 * 100) if brightness is not None else None
            )
            up = choose_dim_direction(
                light_on, brightness_pct, self._last_up, self._min_pct, self._max_pct
            )
            self._last_up = up

            if not light_on:
                # Holding from off: gentle ramp starting at the floor.
                start = self._min_pct
                await self._set_brightness(start)
                await asyncio.sleep(self._step_delay)
            else:
                start = brightness_pct if brightness_pct is not None else self._min_pct

            sweep = DimmerSweep(
                start, up, self._min_pct, self._max_pct, self._step_pct
            )
            while (value := sweep.next_value()) is not None:
                await self._set_brightness(value)
                await asyncio.sleep(self._step_delay)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - a dying dim loop must not go silent
            _LOGGER.warning(
                "Multiway link '%s': dimming failed: %s", self.subentry.title, err
            )

    async def _set_brightness(self, pct: int) -> None:
        # blocking=False: ticks must not stack the target light's latency.
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": self.target_entity_id, "brightness_pct": pct},
            blocking=False,
            context=Context(),
        )

    async def async_teardown(self) -> None:
        self._stop_dimming()
        await super().async_teardown()


async def _apply_climate_action(link: _BaseLink, action: str, mode) -> None:
    """Execute a climate decision from climate_short_press_action."""
    _LOGGER.info(
        "Multiway '%s': -> %s %s", link.subentry.title, action, mode or ""
    )
    if action == "turn_off":
        await link._call_service("climate", "turn_off", link.target_entity_id)
    elif action == "set_mode":
        await link._call_service(
            "climate", "set_hvac_mode", link.target_entity_id, hvac_mode=mode
        )
    elif action == "turn_on":
        await link._call_service("climate", "turn_on", link.target_entity_id)


class SatelliteClimateLink(SatelliteLink):
    """Satellite button bound to a climate device.

    Short press: turn off when running, otherwise recall the last active
    HVAC mode we observed (plain turn_on when none is known yet).
    LED follows on/off (any active mode = on). Long press is unused.
    """

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.satellite = hub.devices.get(subentry.data.get(CONF_KEY_ID))
        self.long_press_scene = None
        self._last_on_mode: str | None = None

    def _target_is_on(self, state: str | None) -> bool | None:
        if state in UNAVAILABLE_STATES:
            return None
        return state != "off"

    def _observe_target(self, state: str | None) -> None:
        if state not in UNAVAILABLE_STATES and state != "off":
            self._last_on_mode = state

    @callback
    def _on_button_event(self, event_type: str) -> None:
        if self.disabled:
            return
        if self._consume_poll_artifact(event_type):
            return
        if event_type == "Short":
            self.hass.async_create_task(self._handle_short_press())

    async def _handle_short_press(self) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        action, mode = climate_short_press_action(
            state.state if state else None, self._last_on_mode
        )
        if action == "none":
            _LOGGER.warning(
                "Multiway '%s': short press ignored, %s is unavailable",
                self.subentry.title,
                self.target_entity_id,
            )
            return
        await _apply_climate_action(self, action, mode)


class BlindLink(_BaseLink):
    """A pair of satellite buttons (up/down) bound to a cover entity.

    Long press: move in the key's direction; while moving, ANY long press
    stops (no auto-reverse). The moving direction's LED is lit while the
    cover reports opening/closing and turns off when movement ends.
    Short press: tilt by a configurable step when the cover supports
    tilt (positional preferred, binary fallback), otherwise stop.
    """

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.up_key = hub.devices.get(subentry.data.get(CONF_UP_KEY_ID))
        self.down_key = hub.devices.get(subentry.data.get(CONF_DOWN_KEY_ID))
        self._tilt_step = int(subentry.data.get(CONF_TILT_STEP, 10))
        self._suppress_first = {True: True, False: True}  # per direction
        # Hybrid motion model: entity-reported motion when available,
        # locally-timed assumption otherwise (one-way covers, Somfy RTS).
        self._motion = BlindMotionTracker(
            float(subentry.data.get(CONF_TRAVEL_TIME, 30))
        )
        self._motion_timeout_task: asyncio.Task | None = None

    async def async_setup(self) -> bool:
        if self.up_key is None or self.down_key is None:
            _LOGGER.warning(
                "Multiway link '%s': up/down key not found; link disabled",
                self.subentry.title,
            )
            self.disabled = True
            return False
        if not self._track_target(self._on_target_state):
            return False
        self.up_key.register_event_callback(self._on_up_event)
        self.down_key.register_event_callback(self._on_down_event)
        await self.resync()
        _LOGGER.debug("Blind link ready: %s", self.subentry.title)
        return True

    async def async_teardown(self) -> None:
        if self._motion_timeout_task and not self._motion_timeout_task.done():
            self._motion_timeout_task.cancel()
        if self.up_key is not None:
            self.up_key.remove_event_callback(self._on_up_event)
        if self.down_key is not None:
            self.down_key.remove_event_callback(self._on_down_event)
        self._base_teardown()

    @callback
    def on_connection_event(self) -> None:
        self._suppress_first = {True: True, False: True}

    @callback
    def _on_up_event(self, event_type: str) -> None:
        self._on_key_event(True, event_type)

    @callback
    def _on_down_event(self, event_type: str) -> None:
        self._on_key_event(False, event_type)

    @callback
    def _on_key_event(self, direction_up: bool, event_type: str) -> None:
        if self.disabled:
            return
        if self._suppress_first[direction_up]:
            self._suppress_first[direction_up] = False
            if event_type != "Release":
                _LOGGER.debug(
                    "Multiway '%s': ignoring first %s after sync (poll artifact)",
                    self.subentry.title,
                    event_type,
                )
            return
        if event_type == "Long":
            self.hass.async_create_task(self._handle_long_press(direction_up))
        elif event_type == "Short":
            self.hass.async_create_task(self._handle_short_press(direction_up))

    async def _handle_long_press(self, direction_up: bool) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        state_str = state.state if state else None
        self._motion.entity_state(state_str)
        action = blind_long_press_action(
            state_str, direction_up, assumed_moving=self._motion.moving
        )
        if action == "none":
            _LOGGER.warning(
                "Multiway '%s': long press ignored, %s is unavailable",
                self.subentry.title,
                self.target_entity_id,
            )
            return
        _LOGGER.info(
            "Multiway '%s': long press (%s) -> %s",
            self.subentry.title,
            "up" if direction_up else "down",
            action,
        )
        service = {
            "open": "open_cover",
            "close": "close_cover",
            "stop": "stop_cover",
        }[action]
        await self._call_service("cover", service, self.target_entity_id)
        if action == "stop":
            self._motion.command_stop()
        else:
            self._motion.command_move(direction_up)
            self._schedule_motion_timeout()
        await self._refresh_leds()

    @callback
    def _schedule_motion_timeout(self) -> None:
        """Clear the LEDs when the assumed travel window elapses."""
        if self._motion_timeout_task and not self._motion_timeout_task.done():
            self._motion_timeout_task.cancel()
        self._motion_timeout_task = self.hass.async_create_task(
            self._motion_timeout()
        )

    async def _motion_timeout(self) -> None:
        await asyncio.sleep(self._motion._travel_time + 0.5)
        await self._refresh_leds()

    async def _handle_short_press(self, direction_up: bool) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        features = state.attributes.get("supported_features") if state else None
        current_tilt = (
            state.attributes.get("current_tilt_position") if state else None
        )
        action, tilt = blind_short_press_action(
            features, direction_up, current_tilt, self._tilt_step
        )
        _LOGGER.info(
            "Multiway '%s': short press (%s) -> %s %s",
            self.subentry.title,
            "up" if direction_up else "down",
            action,
            tilt if tilt is not None else "",
        )
        if action == "set_tilt":
            await self._call_service(
                "cover",
                "set_cover_tilt_position",
                self.target_entity_id,
                tilt_position=tilt,
            )
        elif action == "tilt_open":
            await self._call_service("cover", "open_cover_tilt", self.target_entity_id)
        elif action == "tilt_close":
            await self._call_service(
                "cover", "close_cover_tilt", self.target_entity_id
            )
        else:  # stop
            await self._call_service("cover", "stop_cover", self.target_entity_id)

    async def _on_target_state(self, event: Event) -> None:
        new_state = event.data.get("new_state")
        self._motion.entity_state(new_state.state if new_state else None)
        await self._refresh_leds()

    async def _refresh_leds(self) -> None:
        """Light the LED of the effective movement direction."""
        if self.disabled or not self.hub.supports_led_commands:
            return
        up_led, down_led = blind_led_states(self._motion.direction())
        for satellite, wanted in ((self.up_key, up_led), (self.down_key, down_led)):
            if satellite.indicator_value == wanted:
                continue
            if wanted:
                await satellite.turn_on_indicator()
            else:
                await satellite.turn_off_indicator()

    async def resync(self) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        self._motion.entity_state(state.state if state else None)
        await self._refresh_leds()


class ToggleLink(_BaseLink):
    """Link between a regular toggle key and an entity.

    The HA entity is the MASTER; the Vitrea key is the SLAVE. The key
    follows the entity (including a one-shot alignment after warm-up);
    the entity is commanded only by physical presses (state CHANGES).
    """

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.toggle = hub.devices.get(subentry.data.get(CONF_TOGGLE_ID))
        self.core = ToggleLinkCore()
        self._logged_trips = 0
        self._align_task: asyncio.Task | None = None

    def _entity_is_on(self, state: str | None) -> bool | None:
        """Interpret the master's state as on/off for the core."""
        return _state_to_bool(state)

    def _observe_entity(self, state: str | None) -> None:
        """Hook: subclasses learn from every master state report."""

    async def async_setup(self) -> bool:
        if self.toggle is None:
            _LOGGER.warning(
                "Multiway link '%s': toggle key not found; link disabled",
                self.subentry.title,
            )
            self.disabled = True
            return False
        if not self._track_target(self._on_target_state):
            return False
        self.toggle.register_callback(self._on_key_update)
        await self.resync()
        _LOGGER.debug("Toggle link ready: %s", self.subentry.title)
        return True

    async def async_teardown(self) -> None:
        if self._align_task and not self._align_task.done():
            self._align_task.cancel()
        if self.toggle is not None:
            self.toggle.remove_callback(self._on_key_update)
        self._base_teardown()

    @callback
    def on_connection_event(self) -> None:
        self.core.rearm()

    @callback
    def _on_key_update(self) -> None:
        """The key reported a status (press, echo, or stale re-report)."""
        if self.disabled:
            return
        key_on = bool(self.toggle.is_on)
        decision = self.core.on_key_status(key_on)
        if decision == SYNC_ENTITY:
            # A physical press: forward the human's intent to the master.
            self.hass.async_create_task(self._set_entity(key_on))
        elif decision == SYNC_KEY:
            # Stale slave disagreement: pull the key back to the master.
            self.hass.async_create_task(self._set_key(self.core.last_entity_on))
        elif decision == BREAKER_OPEN:
            self._warn_breaker()

    async def _on_target_state(self, event: Event) -> None:
        if self.disabled:
            return
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        state_str = new_state.state if new_state else None
        self._observe_entity(state_str)
        entity_on = self._entity_is_on(state_str)
        # Restorations (unavailable/unknown -> a real state) are LEARNED,
        # never synced: integrations coming back online routinely restore
        # stale states, and syncing those would actuate real circuits with
        # nobody touching anything.
        if old_state is None or self._entity_is_on(old_state.state) is None:
            self.core.record_entity(entity_on)
            return
        decision = self.core.on_entity_state(entity_on)
        if decision == SYNC_KEY:
            await self._set_key(entity_on)
        elif decision == BREAKER_OPEN:
            self._warn_breaker()

    async def _set_entity(self, is_on: bool) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        # INFO on purpose: every link-initiated actuation must be
        # attributable in default logs when investigating ghost reports.
        _LOGGER.info(
            "Multiway '%s': key press -> setting %s %s",
            self.subentry.title,
            self.target_entity_id,
            "on" if is_on else "off",
        )
        service = "turn_on" if is_on else "turn_off"
        await self._call_service("homeassistant", service, self.target_entity_id)

    async def _set_key(self, is_on: bool) -> None:
        if self.disabled:
            return
        _LOGGER.info(
            "Multiway '%s': master state -> setting key %s",
            self.subentry.title,
            "on" if is_on else "off",
        )
        if is_on:
            await self.toggle.turn_on()
        else:
            await self.toggle.turn_off()

    def _warn_breaker(self) -> None:
        if self.core.breaker.trip_count > self._logged_trips:
            self._logged_trips = self.core.breaker.trip_count
            _LOGGER.warning(
                "Multiway link '%s' suspended briefly: rapid on/off oscillation "
                "detected and cut by the safety breaker",
                self.subentry.title,
            )

    async def resync(self) -> None:
        """Record both sides, re-enter warm-up, and schedule the one-shot
        alignment. Nothing is actuated until the warm-up absorbs the
        boot/reconnect storms; then the slave (key) is brought in line
        with the master (entity) if they still differ."""
        if self.disabled or self.target_entity_id is None:
            return
        state = self.hass.states.get(self.target_entity_id)
        state_str = state.state if state else None
        self._observe_entity(state_str)
        self.core.seed(bool(self.toggle.is_on), self._entity_is_on(state_str))
        if self._align_task and not self._align_task.done():
            self._align_task.cancel()
        self._align_task = self.hass.async_create_task(self._align_after_warmup())

    async def _align_after_warmup(self) -> None:
        await asyncio.sleep(ToggleLinkCore.WARMUP_SECONDS + 0.5)
        if self.disabled or self.target_entity_id is None:
            return
        # Refresh the master's current state before deciding.
        state = self.hass.states.get(self.target_entity_id)
        state_str = state.state if state else None
        self._observe_entity(state_str)
        self.core.record_entity(self._entity_is_on(state_str))
        decision = self.core.alignment_check()
        if decision == SYNC_KEY:
            _LOGGER.info(
                "Multiway '%s': post-warmup alignment", self.subentry.title
            )
            await self._set_key(self.core.last_entity_on)
        elif decision == BREAKER_OPEN:
            self._warn_breaker()


class ToggleClimateLink(ToggleLink):
    """Toggle key bound to a climate device (HA is master, key is slave).

    Flipping the key on recalls the climate's last active HVAC mode
    (plain turn_on when none is known); flipping it off turns the
    climate off. The key follows the climate's running state, with the
    full loop-safety machinery (baselines, echoes, warm-up, breaker).
    """

    def __init__(self, hass, hub, subentry: ConfigSubentry) -> None:
        super().__init__(hass, hub, subentry)
        self.toggle = hub.devices.get(subentry.data.get(CONF_KEY_ID))
        self._last_on_mode: str | None = None

    def _entity_is_on(self, state: str | None) -> bool | None:
        if state in UNAVAILABLE_STATES:
            return None
        return state != "off"

    def _observe_entity(self, state: str | None) -> None:
        if state not in UNAVAILABLE_STATES and state != "off":
            self._last_on_mode = state

    async def _set_entity(self, is_on: bool) -> None:
        if self.disabled or self.target_entity_id is None:
            return
        if is_on:
            action, mode = climate_short_press_action("off", self._last_on_mode)
        else:
            action, mode = ("turn_off", None)
        await _apply_climate_action(self, action, mode)


class LinkManager:
    """Owns all links of a config entry; rebuilds on reload.

    The kill-switch entity (switch.VitreaMultiwayKillSwitch) drives
    `async_set_enabled`: pausing tears every link down completely —
    no subscriptions, no key callbacks, no LED writes — so a paused
    integration cannot actuate anything no matter what arrives on the
    wire. Resuming rebuilds the links through the normal setup path,
    which seeds record-only and re-enters warm-up, so the act of
    resuming never actuates by itself.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub) -> None:
        self.hass = hass
        self.entry = entry
        self.hub = hub
        self.links: dict[str, _BaseLink] = {}
        self.enabled = True
        self._toggle_lock = asyncio.Lock()
        self._resync_task: asyncio.Task | None = None

    async def async_setup(self) -> None:
        if not self.enabled:
            _LOGGER.info("Multiway: links paused by the kill-switch; not building")
            return
        for subentry in self.entry.subentries.values():
            if subentry.subentry_type == SUBENTRY_TYPE_SATELLITE_LINK:
                link: _BaseLink = SatelliteLink(self.hass, self.hub, subentry)
            elif subentry.subentry_type == SUBENTRY_TYPE_SATELLITE_LIGHT_LINK:
                link = SatelliteLightLink(self.hass, self.hub, subentry)
            elif subentry.subentry_type == SUBENTRY_TYPE_CLIMATE_LINK:
                link = self._build_climate_link(subentry)
                if link is None:
                    continue
            elif subentry.subentry_type == SUBENTRY_TYPE_BLIND_LINK:
                link = BlindLink(self.hass, self.hub, subentry)
            elif subentry.subentry_type == SUBENTRY_TYPE_TOGGLE_LINK:
                link = ToggleLink(self.hass, self.hub, subentry)
            else:
                continue
            await link.async_setup()
            self.links[subentry.subentry_id] = link
        if self.links:
            self.hub.controller.register_callback(self._on_controller_event)
            _LOGGER.info("Multiway: %d link(s) active", len(self.links))

    def _build_climate_link(self, subentry: ConfigSubentry) -> _BaseLink | None:
        """Climate links accept a satellite OR a toggle key as the source."""
        from .hub import SatelliteButton

        source = self.hub.devices.get(subentry.data.get(CONF_KEY_ID))
        if isinstance(source, SatelliteButton):
            return SatelliteClimateLink(self.hass, self.hub, subentry)
        if source is not None and hasattr(source, "is_on"):
            return ToggleClimateLink(self.hass, self.hub, subentry)
        _LOGGER.warning(
            "Multiway link '%s': source key not found; link skipped",
            subentry.title,
        )
        return None

    async def async_teardown(self) -> None:
        await self._async_teardown_links()

    async def _async_teardown_links(self) -> None:
        if self.links:
            self.hub.controller.remove_callback(self._on_controller_event)
        if self._resync_task and not self._resync_task.done():
            self._resync_task.cancel()
        for link in self.links.values():
            # In-flight handler tasks (created just before teardown) check
            # this flag; flipping it first closes the last actuation window.
            link.disabled = True
            await link.async_teardown()
        self.links.clear()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Kill-switch: pause (teardown) or resume (rebuild) all links."""
        async with self._toggle_lock:
            if enabled == self.enabled:
                return
            self.enabled = enabled
            if enabled:
                _LOGGER.info("Multiway kill-switch: resuming links")
                await self.async_setup()
            else:
                _LOGGER.info("Multiway kill-switch: pausing all links")
                await self._async_teardown_links()

    @callback
    def restore_paused(self) -> None:
        """The kill-switch entity restored an 'off' state at startup.

        Runs while platforms are being set up — before async_setup builds
        the links — so normally this only flips the flag. If links were
        somehow already built, tear them down.
        """
        if not self.enabled:
            return
        self.enabled = False
        _LOGGER.info("Multiway: links stay paused (kill-switch was off)")
        if self.links:
            self.hass.async_create_task(self._async_teardown_links())

    async def _on_controller_event(self, result: dict) -> None:
        """Re-arm all links on any connection change; resync after reconnect."""
        if result.get("type") != "connection":
            return
        # Immediately: the very next status burst is a poll baseline, not
        # user activity — regardless of how long it takes to arrive.
        for link in self.links.values():
            link.on_connection_event()
        if not result.get("status"):
            return
        if self._resync_task and not self._resync_task.done():
            return
        self._resync_task = self.hass.async_create_task(self._delayed_resync())

    async def _delayed_resync(self) -> None:
        await asyncio.sleep(RESYNC_DELAY)  # let the NALL:G sync land first
        for link in self.links.values():
            await link.resync()
