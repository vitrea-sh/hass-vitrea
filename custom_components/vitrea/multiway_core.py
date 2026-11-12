"""Loop-safe decision core for Multiway links.

Pure logic, no Home Assistant imports — fully unit-testable. The link
wrappers in multiway.py feed observations in and execute the returned
decisions.

Three independent safety layers prevent the on-off-on-off oscillation:

1. Echo suppression: every state we set on one side registers an
   expectation; when the resulting confirmation arrives, it is consumed
   and NOT treated as a new change.
2. Idempotence: a change that already matches the other side is a no-op
   (uses the event payload, never a re-read of possibly-stale state).
3. Circuit breaker: a hard cap on link-initiated actions per time
   window; if something unforeseen still bounces, the link suspends
   itself for a cooldown instead of oscillating.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

# Decisions returned to the wrapper. The wrapper MUST perform the action
# for SYNC_* results (the core has already registered the echo
# expectation for it) and must do nothing for the rest.
SYNC_ENTITY = "sync_entity"
SYNC_KEY = "sync_key"
ECHO = "echo"
IN_SYNC = "in_sync"
BREAKER_OPEN = "breaker_open"
UNKNOWN = "unknown"
WARMUP = "warmup"
RECORDED = "recorded"


UNAVAILABLE_STATES = (None, "unavailable", "unknown")


def climate_short_press_action(
    current_state: Optional[str], last_on_mode: Optional[str]
) -> tuple[str, Optional[str]]:
    """Decide the short-press action for a satellite-climate link.

    On -> turn off. Off -> recall the last active HVAC mode we observed
    (or a plain turn_on when none is known). Unavailable -> do nothing.
    """
    if current_state in UNAVAILABLE_STATES:
        return ("none", None)
    if current_state == "off":
        if last_on_mode:
            return ("set_mode", last_on_mode)
        return ("turn_on", None)
    return ("turn_off", None)


# HA CoverEntityFeature bits (stable public constants).
COVER_OPEN_TILT = 16
COVER_CLOSE_TILT = 32
COVER_SET_TILT_POSITION = 128

MOVING_STATES = ("opening", "closing")


def blind_long_press_action(
    state: Optional[str], direction_up: bool, assumed_moving: bool = False
) -> str:
    """Long press on an up/down key: move in the key's direction, or stop
    if the cover is moving — reported OR locally assumed (one-way covers
    like Somfy RTS never report motion; without the assumption a second
    long press would re-issue the move instead of stopping)."""
    if state in UNAVAILABLE_STATES:
        return "none"
    if state in MOVING_STATES or assumed_moving:
        return "stop"
    return "open" if direction_up else "close"


class BlindMotionTracker:
    """Effective motion for a cover that may or may not report motion.

    Entity-reported opening/closing is authoritative. Covers that never
    report motion (one-way RF, assumed-state) get a local assumption: a
    movement WE commanded counts as active until we stop it or the
    configured travel time elapses. The tracker self-learns: once an
    entity has ever reported motion, its settled states are trusted to
    end movement — until then, the instant 'closed' echo an
    assumed-state integration emits right after a command is ignored.
    """

    def __init__(self, travel_time: float, clock: Callable[[], float] = time.monotonic):
        self._travel_time = travel_time
        self._clock = clock
        self._local_dir: Optional[bool] = None  # True = up
        self._local_until = 0.0
        self._entity_dir: Optional[bool] = None
        self.entity_reports_motion = False

    def command_move(self, direction_up: bool) -> None:
        self._local_dir = direction_up
        self._local_until = self._clock() + self._travel_time

    def command_stop(self) -> None:
        self._local_dir = None

    def entity_state(self, state: Optional[str]) -> None:
        if state == "opening":
            self._entity_dir = True
            self.entity_reports_motion = True
        elif state == "closing":
            self._entity_dir = False
            self.entity_reports_motion = True
        else:
            self._entity_dir = None
            if self.entity_reports_motion and state not in UNAVAILABLE_STATES:
                # A motion-capable entity settled: movement really ended.
                self._local_dir = None

    def direction(self) -> Optional[bool]:
        """Current effective direction: True=up, False=down, None=idle."""
        if self._entity_dir is not None:
            return self._entity_dir
        if self._local_dir is not None and self._clock() < self._local_until:
            return self._local_dir
        return None

    @property
    def moving(self) -> bool:
        return self.direction() is not None


def blind_short_press_action(
    supported_features: Optional[int],
    direction_up: bool,
    current_tilt: Optional[int],
    step_pct: int,
) -> tuple[str, Optional[int]]:
    """Short press: tilt by a step when the cover supports it, else stop.

    Positional tilt steps from the current tilt (50 assumed when the
    cover hasn't reported one), clamped to 0-100. Covers with only
    binary tilt get full open/close tilt. No tilt support -> stop.
    """
    features = supported_features or 0
    if features & COVER_SET_TILT_POSITION:
        base = current_tilt if current_tilt is not None else 50
        delta = step_pct if direction_up else -step_pct
        return ("set_tilt", max(0, min(100, base + delta)))
    if direction_up and features & COVER_OPEN_TILT:
        return ("tilt_open", None)
    if not direction_up and features & COVER_CLOSE_TILT:
        return ("tilt_close", None)
    return ("stop", None)


def blind_led_states(direction_up: Optional[bool]) -> tuple[bool, bool]:
    """(up_led, down_led) for an effective motion direction."""
    if direction_up is True:
        return (True, False)
    if direction_up is False:
        return (False, True)
    return (False, False)


class ExpectationTracker:
    """FIFO of expected confirmations with a TTL.

    When the link sets a state on one side, the resulting status/event
    that comes back must not be mistaken for a user action. Expectations
    expire so a lost confirmation can never suppress a later real one.
    """

    def __init__(self, ttl: float, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._pending: list[tuple[bool, float]] = []

    def expect(self, state: bool) -> None:
        self._pending.append((state, self._clock() + self._ttl))

    def consume(self, state: bool) -> bool:
        """Return True (and consume one expectation) if this state was expected."""
        now = self._clock()
        self._pending = [(s, d) for (s, d) in self._pending if d >= now]
        for index, (expected, _) in enumerate(self._pending):
            if expected == state:
                del self._pending[index]
                return True
        return False

    def __len__(self) -> int:
        now = self._clock()
        return sum(1 for (_, d) in self._pending if d >= now)


class CircuitBreaker:
    """Hard cap on link actions: max_actions per window, else open for cooldown."""

    def __init__(
        self,
        max_actions: int = 8,
        window: float = 10.0,
        cooldown: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._max_actions = max_actions
        self._window = window
        self._cooldown = cooldown
        self._clock = clock
        self._actions: list[float] = []
        self._open_until = 0.0
        self.trip_count = 0

    @property
    def is_open(self) -> bool:
        return self._clock() < self._open_until

    def allow(self) -> bool:
        """Return True if another action may run; trips the breaker at the cap."""
        now = self._clock()
        if now < self._open_until:
            return False
        self._actions = [t for t in self._actions if t > now - self._window]
        if len(self._actions) >= self._max_actions:
            self._open_until = now + self._cooldown
            self.trip_count += 1
            self._actions.clear()
            return False
        return True

    def record(self) -> None:
        self._actions.append(self._clock())


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def choose_dim_direction(
    light_on: bool,
    brightness_pct: Optional[int],
    last_up: Optional[bool],
    min_pct: int,
    max_pct: int,
) -> bool:
    """Pick the sweep direction for a long-press session (True = up).

    Off lights always ramp up; lights parked at a bound sweep away from
    it; otherwise alternate with the previous session (first hold on a
    lit light dims down — the common wall-dimmer expectation).
    """
    if not light_on:
        return True
    if brightness_pct is not None:
        if brightness_pct >= max_pct:
            return False
        if brightness_pct <= min_pct:
            return True
    if last_up is None:
        return False
    return not last_up


class DimmerSweep:
    """Bounded brightness sweep for one long-press dimming session.

    Yields absolute brightness percentages from a virtual position, so
    slow lights can't lag the loop into compounding errors, stepping
    below the floor can't switch the light off, and the sweep is
    finite by construction: it ends at the min/max bound even if the
    Release event is lost.
    """

    def __init__(
        self,
        start_pct: int,
        direction_up: bool,
        min_pct: int,
        max_pct: int,
        step_pct: int,
    ):
        self._min = min_pct
        self._max = max_pct
        self._step = max(1, step_pct)
        self._up = direction_up
        self._pos = clamp(start_pct, min_pct, max_pct)

    @property
    def position(self) -> int:
        return self._pos

    def next_value(self) -> Optional[int]:
        """Return the next brightness percentage, or None at the bound."""
        target = self._pos + self._step if self._up else self._pos - self._step
        target = clamp(target, self._min, self._max)
        if target == self._pos:
            return None
        self._pos = target
        return target


class ToggleLinkCore:
    """Decision engine for a key <-> entity link.

    Roles: the HA entity is the MASTER, the Vitrea key is the SLAVE.
    Reconciliation of any mismatch writes toward the key only; the master
    is commanded exclusively when a human presses the key (a state
    CHANGE, which is intent, not reconciliation).

    The wrapper reports observations; the returned decision says what to
    do. For SYNC_ENTITY / SYNC_KEY the corresponding echo expectation has
    already been registered, so the wrapper must follow through
    (SYNC_KEY always means "set the key to last_entity_on").
    """

    # Confirmations: a vBox status echo is fast (LAN round-trip); an HA
    # entity can be slow (e.g. a cloud device confirming after seconds).
    KEY_ECHO_TTL = 3.0
    ENTITY_ECHO_TTL = 5.0
    # After setup/reload/reconnect the link only LEARNS states for this
    # long: it absorbs the NALL:G status burst and entity restoration
    # storms without actuating anything. Only human-time changes sync.
    WARMUP_SECONDS = 5.0

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._key_echo = ExpectationTracker(self.KEY_ECHO_TTL, clock)
        self._entity_echo = ExpectationTracker(self.ENTITY_ECHO_TTL, clock)
        self.breaker = CircuitBreaker(clock=clock)
        self.last_key_on: Optional[bool] = None
        self.last_entity_on: Optional[bool] = None
        self._armed_at = clock() + self.WARMUP_SECONDS
        self._baseline_pending = True

    @property
    def armed(self) -> bool:
        return self._clock() >= self._armed_at

    def seed(self, key_on: Optional[bool], entity_on: Optional[bool]) -> str:
        """Record both sides and (re)enter warm-up. NEVER actuates directly.

        Boot/reload/reconnect must not act on possibly-stale states: the
        warm-up absorbs the NALL:G burst and restoration storms. Call
        alignment_check() once warm-up has elapsed to bring the slave
        (key) in line with the master (entity) if they still differ.
        """
        self.last_key_on = key_on
        self.last_entity_on = entity_on
        self._armed_at = self._clock() + self.WARMUP_SECONDS
        self._baseline_pending = True
        return RECORDED

    def rearm(self) -> str:
        """Re-enter warm-up and expect a new poll baseline, keeping the
        learned states. Called on every connection event: the reconnect's
        NALL:G burst must never be read as presses."""
        self._armed_at = self._clock() + self.WARMUP_SECONDS
        self._baseline_pending = True
        return RECORDED

    def record_entity(self, entity_on: Optional[bool]) -> str:
        """Learn the master's state without syncing (restorations: an
        integration coming back from unavailable may report stale state)."""
        self.last_entity_on = entity_on
        return RECORDED

    def alignment_check(self) -> str:
        """One-shot post-warmup reconciliation: slave follows master."""
        if not self.armed:
            return WARMUP
        if self.last_entity_on is None:
            return UNKNOWN
        if self.last_key_on == self.last_entity_on:
            return IN_SYNC
        if not self.breaker.allow():
            return BREAKER_OPEN
        self.breaker.record()
        self._key_echo.expect(self.last_entity_on)
        return SYNC_KEY

    def on_key_status(self, key_on: bool) -> str:
        """A status frame for the key arrived.

        A CHANGE is a physical press: forward the human's intent to the
        master (SYNC_ENTITY). A re-report that mismatches the master is
        reconciliation: pull the slave back (SYNC_KEY) — the master is
        never written from its own side's stale disagreement.
        """
        changed = self.last_key_on is not None and key_on != self.last_key_on
        self.last_key_on = key_on
        if self._key_echo.consume(key_on):
            return ECHO
        if self._baseline_pending:
            # First report after a (re)connect/reload is the NALL:G poll's
            # baseline for this key — never a press. This is what makes the
            # link immune to arbitrarily slow status bursts (observed live:
            # ~600ms per key, a 25s burst that outlives any time window).
            self._baseline_pending = False
            return RECORDED
        if not self.armed:
            return WARMUP
        if self.last_entity_on is None:
            return UNKNOWN
        if key_on == self.last_entity_on:
            return IN_SYNC
        if not self.breaker.allow():
            return BREAKER_OPEN
        self.breaker.record()
        if changed:
            self._entity_echo.expect(key_on)
            return SYNC_ENTITY
        self._key_echo.expect(self.last_entity_on)
        return SYNC_KEY

    def on_entity_state(self, entity_on: Optional[bool]) -> str:
        """The master's state was reported (payload from the event).

        Any mismatch with the slave resolves toward the slave: the key
        follows the entity. The entity is never commanded from here.
        """
        if entity_on is None:
            # unavailable/unknown: remember nothing actionable, never sync.
            self.last_entity_on = None
            return UNKNOWN
        self.last_entity_on = entity_on
        if self._entity_echo.consume(entity_on):
            return ECHO
        if not self.armed:
            return WARMUP
        if self.last_key_on is not None and entity_on == self.last_key_on:
            return IN_SYNC
        if not self.breaker.allow():
            return BREAKER_OPEN
        self.breaker.record()
        self._key_echo.expect(entity_on)
        return SYNC_KEY
