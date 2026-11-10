"""Loop-safety proofs for the Multiway link decision core.

The critical requirement: a key<->entity link must NEVER oscillate
on-off-on-off. Three layers are tested independently and together,
including a forced adversarial loop that must be cut by the breaker.
"""

from multiway_core import (
    BREAKER_OPEN,
    ECHO,
    IN_SYNC,
    RECORDED,
    SYNC_ENTITY,
    SYNC_KEY,
    UNKNOWN,
    WARMUP,
    CircuitBreaker,
    DimmerSweep,
    ExpectationTracker,
    ToggleLinkCore,
    choose_dim_direction,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- ExpectationTracker ---


def test_expectation_consumed_once():
    clock = FakeClock()
    tracker = ExpectationTracker(ttl=3.0, clock=clock)
    tracker.expect(True)
    assert tracker.consume(True) is True
    assert tracker.consume(True) is False  # only one expectation


def test_expectation_state_must_match():
    tracker = ExpectationTracker(ttl=3.0, clock=FakeClock())
    tracker.expect(True)
    assert tracker.consume(False) is False
    assert tracker.consume(True) is True


def test_expectation_expires():
    clock = FakeClock()
    tracker = ExpectationTracker(ttl=3.0, clock=clock)
    tracker.expect(True)
    clock.advance(3.1)
    assert tracker.consume(True) is False


# --- CircuitBreaker ---


def test_breaker_allows_up_to_cap_then_trips():
    clock = FakeClock()
    breaker = CircuitBreaker(max_actions=3, window=10.0, cooldown=30.0, clock=clock)
    for _ in range(3):
        assert breaker.allow()
        breaker.record()
    assert breaker.allow() is False
    assert breaker.is_open
    assert breaker.trip_count == 1


def test_breaker_reopens_after_cooldown():
    clock = FakeClock()
    breaker = CircuitBreaker(max_actions=2, window=10.0, cooldown=30.0, clock=clock)
    for _ in range(2):
        breaker.allow()
        breaker.record()
    assert breaker.allow() is False
    clock.advance(30.1)
    assert breaker.allow() is True


def test_breaker_window_slides():
    clock = FakeClock()
    breaker = CircuitBreaker(max_actions=2, window=10.0, cooldown=30.0, clock=clock)
    breaker.allow()
    breaker.record()
    clock.advance(11)  # first action leaves the window
    breaker.allow()
    breaker.record()
    assert breaker.allow() is True  # still only one action in window


# --- ToggleLinkCore: normal flows ---


def armed_core(clock: FakeClock, key_on=False, entity_on=False) -> ToggleLinkCore:
    """Seeded core, warm-up elapsed, poll baseline already consumed."""
    core = ToggleLinkCore(clock=clock)
    core.seed(key_on=key_on, entity_on=entity_on)
    clock.advance(ToggleLinkCore.WARMUP_SECONDS + 1)
    # NALL:G reports each key exactly once after connecting; that first
    # report is the baseline and is never interpreted as a press.
    assert core.on_key_status(bool(key_on)) == RECORDED
    return core


def test_key_press_syncs_entity_and_echo_is_swallowed():
    core = armed_core(FakeClock(), key_on=False, entity_on=False)

    assert core.on_key_status(True) == SYNC_ENTITY
    # HA confirms the entity turned on — must NOT bounce back to the key.
    assert core.on_entity_state(True) == ECHO


def test_entity_change_syncs_key_and_echo_is_swallowed():
    core = armed_core(FakeClock(), key_on=False, entity_on=False)

    assert core.on_entity_state(True) == SYNC_KEY
    # The vBox echoes the key's new state — must NOT bounce to the entity.
    assert core.on_key_status(True) == ECHO


def test_matching_states_are_noops():
    core = armed_core(FakeClock(), key_on=True, entity_on=True)
    assert core.on_key_status(True) == IN_SYNC
    assert core.on_entity_state(True) == IN_SYNC


def test_unavailable_entity_never_syncs():
    core = armed_core(FakeClock(), key_on=True, entity_on=True)
    assert core.on_entity_state(None) == UNKNOWN
    # Recovering with a real state works again.
    assert core.on_entity_state(False) == SYNC_KEY


def test_slow_entity_confirmation_after_ttl_still_no_bounce():
    clock = FakeClock()
    core = armed_core(clock, key_on=False, entity_on=False)

    assert core.on_key_status(True) == SYNC_ENTITY
    clock.advance(ToggleLinkCore.ENTITY_ECHO_TTL + 1)  # echo expectation expired
    # Layer 2 (idempotence vs last key state) still prevents the bounce.
    assert core.on_entity_state(True) == IN_SYNC


# --- Seeding and warm-up: links must never actuate outside human time ---
# (Seen in the field: another integration restored a stale "on" during
# reload storms, and an entity-wins seed switched a real circuit with
# nobody touching anything.)


def test_seed_never_actuates():
    core = ToggleLinkCore(clock=FakeClock())
    assert core.seed(key_on=False, entity_on=True) == RECORDED
    assert core.seed(key_on=True, entity_on=False) == RECORDED
    assert core.seed(key_on=None, entity_on=None) == RECORDED


def test_warmup_absorbs_boot_bursts_then_arms():
    clock = FakeClock()
    core = ToggleLinkCore(clock=clock)
    core.seed(key_on=False, entity_on=False)

    # First key report = poll baseline; further burst traffic during the
    # warm-up is learned, never acted on.
    assert core.on_key_status(True) == RECORDED
    assert core.on_key_status(False) == WARMUP
    assert core.on_entity_state(False) == WARMUP
    assert not core.armed

    clock.advance(ToggleLinkCore.WARMUP_SECONDS + 1)
    assert core.armed
    # A real change after warm-up syncs normally.
    assert core.on_key_status(False) == IN_SYNC  # matches entity=False
    assert core.on_key_status(True) == SYNC_ENTITY


def test_slow_poll_burst_cannot_fake_presses():
    """Regression for a field case: the vBox
    streamed the NALL:G burst at ~600ms/key (~25s total), far past any
    time-based warm-up. The first post-connect report per key must be a
    baseline even when it arrives long after warm-up expired."""
    clock = FakeClock()
    core = ToggleLinkCore(clock=clock)
    core.seed(key_on=False, entity_on=False)  # model still default-off

    clock.advance(ToggleLinkCore.WARMUP_SECONDS + 20)  # burst still going
    # The late NALL report of the key's true state: baseline, NOT a press.
    assert core.on_key_status(True) == RECORDED

    # Real presses afterwards work exactly as intended.
    assert core.on_key_status(False) == IN_SYNC  # matches entity=False
    assert core.on_key_status(True) == SYNC_ENTITY


def test_rearm_on_reconnect_expects_new_baseline():
    core = armed_core(FakeClock(), key_on=False, entity_on=False)
    assert core.on_key_status(True) == SYNC_ENTITY  # normal press works
    core.on_entity_state(True)  # echo

    core.rearm()  # connection dropped/reconnected
    # The reconnect poll's report — even a surprising one — is baseline.
    assert core.on_key_status(False) == RECORDED
    # And afterwards the link is live again (post-warmup).
    assert not core.armed


def test_restoration_is_recorded_never_synced():
    core = armed_core(FakeClock(), key_on=True, entity_on=True)
    # Integration came back (unavailable -> off) with a stale state:
    # the wrapper routes it to record_entity — learn only.
    assert core.record_entity(False) == RECORDED
    # The learned state is used for idempotence going forward.
    assert core.on_key_status(False) == IN_SYNC


def test_boot_desync_aligns_slave_to_master_after_warmup():
    clock = FakeClock()
    core = ToggleLinkCore(clock=clock)
    # Desynced at boot: key on, entity off. Nothing happens during warm-up...
    assert core.seed(key_on=True, entity_on=False) == RECORDED
    assert core.alignment_check() == WARMUP
    clock.advance(ToggleLinkCore.WARMUP_SECONDS + 1)
    # ...then the one-shot alignment pulls the KEY (slave) to the entity
    # (master) — never the other way around.
    assert core.alignment_check() == SYNC_KEY
    assert core.on_key_status(False) == ECHO  # the resulting echo is inert
    assert core.alignment_check() == IN_SYNC


# --- Master/slave doctrine: reconciliation writes toward the key only ---


def test_key_rereport_mismatch_pulls_slave_back_not_master():
    # Key reports its (unchanged) state disagreeing with the master:
    # that is stale-slave reconciliation, so the KEY gets corrected;
    # the entity must never be commanded by it.
    core = armed_core(FakeClock(), key_on=True, entity_on=False)
    assert core.on_key_status(True) == SYNC_KEY  # not SYNC_ENTITY
    assert core.on_key_status(False) == ECHO


def test_entity_side_never_commands_the_master():
    core = armed_core(FakeClock(), key_on=True, entity_on=True)
    # Master re-reports/changes: the only possible action is toward the key.
    assert core.on_entity_state(False) == SYNC_KEY
    assert core.on_key_status(False) == ECHO
    assert core.on_entity_state(False) == IN_SYNC


def test_key_press_with_unknown_master_does_nothing():
    core = armed_core(FakeClock(), key_on=False, entity_on=False)
    core.on_entity_state(None)  # master went unavailable
    assert core.on_key_status(True) == UNKNOWN  # no blind actuation


# --- Satellite-climate link decisions ---


def test_climate_short_press_decisions():
    from multiway_core import climate_short_press_action

    # On (any active mode) -> turn off.
    assert climate_short_press_action("heat", "cool") == ("turn_off", None)
    assert climate_short_press_action("cool", None) == ("turn_off", None)
    # Off -> recall last active mode; plain turn_on when none known.
    assert climate_short_press_action("off", "heat") == ("set_mode", "heat")
    assert climate_short_press_action("off", None) == ("turn_on", None)
    # Unavailable -> never actuate blindly.
    assert climate_short_press_action("unavailable", "heat") == ("none", None)
    assert climate_short_press_action(None, "heat") == ("none", None)


# --- Blind link decisions (up/down satellite pair) ---


def test_blind_long_press_moves_or_stops():
    from multiway_core import blind_long_press_action

    # Idle: move in the key's direction.
    assert blind_long_press_action("open", True) == "open"
    assert blind_long_press_action("closed", True) == "open"
    assert blind_long_press_action("open", False) == "close"
    # Moving: ANY long press stops, both keys, both directions.
    assert blind_long_press_action("opening", True) == "stop"
    assert blind_long_press_action("opening", False) == "stop"
    assert blind_long_press_action("closing", True) == "stop"
    # One-way covers (Somfy RTS): the LOCAL motion assumption also stops —
    # even when the assumed-state entity claims a settled state.
    assert blind_long_press_action("closed", True, assumed_moving=True) == "stop"
    assert blind_long_press_action("open", False, assumed_moving=True) == "stop"
    # Unavailable: never actuate blindly.
    assert blind_long_press_action("unavailable", True) == "none"
    assert blind_long_press_action(None, False) == "none"


def test_blind_motion_tracker_local_assumption():
    from multiway_core import BlindMotionTracker

    clock = FakeClock()
    tracker = BlindMotionTracker(travel_time=30, clock=clock)

    assert tracker.direction() is None
    tracker.command_move(True)
    assert tracker.direction() is True
    # An assumed-state cover echoing 'closed' instantly must NOT end the
    # local assumption (it has never reported motion).
    tracker.entity_state("open")
    assert tracker.direction() is True
    # Our stop ends it.
    tracker.command_stop()
    assert tracker.direction() is None
    # And the travel window ends it on its own.
    tracker.command_move(False)
    clock.advance(31)
    assert tracker.direction() is None


def test_blind_motion_tracker_trusts_motion_capable_entities():
    from multiway_core import BlindMotionTracker

    clock = FakeClock()
    tracker = BlindMotionTracker(travel_time=30, clock=clock)

    tracker.command_move(True)
    tracker.entity_state("opening")  # entity confirms: it reports motion
    assert tracker.entity_reports_motion
    assert tracker.direction() is True
    # A settled report from a motion-capable entity ends movement — both
    # the reported and the local assumption.
    tracker.entity_state("open")
    assert tracker.direction() is None
    # Externally started movement is picked up too.
    tracker.entity_state("closing")
    assert tracker.direction() is False


def test_blind_motion_tracker_unavailable_keeps_local():
    from multiway_core import BlindMotionTracker

    tracker = BlindMotionTracker(travel_time=30, clock=FakeClock())
    tracker.command_move(True)
    tracker.entity_state("opening")
    tracker.entity_state("unavailable")  # blip must not fake a settle
    assert tracker.direction() is True  # local assumption still active


def test_blind_short_press_tilt_and_fallbacks():
    from multiway_core import (
        COVER_CLOSE_TILT,
        COVER_OPEN_TILT,
        COVER_SET_TILT_POSITION,
        blind_short_press_action,
    )

    # Positional tilt: step from current, clamped.
    assert blind_short_press_action(COVER_SET_TILT_POSITION, True, 40, 10) == (
        "set_tilt",
        50,
    )
    assert blind_short_press_action(COVER_SET_TILT_POSITION, False, 40, 10) == (
        "set_tilt",
        30,
    )
    assert blind_short_press_action(COVER_SET_TILT_POSITION, True, 95, 10) == (
        "set_tilt",
        100,
    )
    assert blind_short_press_action(COVER_SET_TILT_POSITION, False, 5, 10) == (
        "set_tilt",
        0,
    )
    # Unknown current tilt: assume mid-range.
    assert blind_short_press_action(COVER_SET_TILT_POSITION, True, None, 10) == (
        "set_tilt",
        60,
    )
    # Binary tilt only.
    features = COVER_OPEN_TILT | COVER_CLOSE_TILT
    assert blind_short_press_action(features, True, None, 10) == ("tilt_open", None)
    assert blind_short_press_action(features, False, None, 10) == ("tilt_close", None)
    # One-sided binary tilt: the unsupported direction stops instead.
    assert blind_short_press_action(COVER_OPEN_TILT, False, None, 10) == ("stop", None)
    # No tilt at all -> short press stops the blind.
    assert blind_short_press_action(0, True, None, 10) == ("stop", None)
    assert blind_short_press_action(None, False, None, 10) == ("stop", None)


def test_blind_led_states():
    from multiway_core import blind_led_states

    assert blind_led_states(True) == (True, False)  # moving up
    assert blind_led_states(False) == (False, True)  # moving down
    assert blind_led_states(None) == (False, False)  # idle


# --- The forced oscillation: must be cut by the breaker ---


def test_adversarial_fast_loop_is_cut_by_breaker():
    """Simulate the worst case: both sides fight the link with instant,
    always-mismatched reports (echo suppression defeated by design).
    The breaker must cut the loop after its action cap, and every
    further attempt must be refused."""
    core = armed_core(FakeClock(), key_on=False, entity_on=False)

    actions = 0
    decisions = []
    state = True
    for round_number in range(40):
        # Alternate adversarial reports that always mismatch the other side.
        if round_number % 2 == 0:
            decision = core.on_entity_state(state)
        else:
            decision = core.on_key_status(not state)
            state = not state
        decisions.append(decision)
        if decision in (SYNC_ENTITY, SYNC_KEY):
            actions += 1

    max_actions = core.breaker._max_actions
    assert actions <= max_actions, (
        f"loop performed {actions} actions — breaker failed to cut it"
    )
    assert core.breaker.trip_count >= 1
    assert decisions[-1] == BREAKER_OPEN


# --- Dimming: bounded sweeps and direction choice ---


def drain(sweep: DimmerSweep) -> list[int]:
    values = []
    while (value := sweep.next_value()) is not None:
        values.append(value)
        assert len(values) <= 200, "sweep must be finite by construction"
    return values


def test_sweep_up_ends_at_max():
    sweep = DimmerSweep(start_pct=20, direction_up=True, min_pct=1, max_pct=100, step_pct=20)
    assert drain(sweep) == [40, 60, 80, 100]
    assert sweep.next_value() is None  # stays done


def test_sweep_down_ends_at_min_never_zero():
    sweep = DimmerSweep(start_pct=50, direction_up=False, min_pct=10, max_pct=100, step_pct=20)
    # Clamps to the floor — never steps to 0 (which would switch the light off).
    assert drain(sweep) == [30, 10]


def test_sweep_bounded_even_if_release_is_lost():
    sweep = DimmerSweep(start_pct=1, direction_up=True, min_pct=1, max_pct=100, step_pct=1)
    values = drain(sweep)
    assert len(values) == 99  # exactly the range, then stops on its own


def test_sweep_start_outside_bounds_is_clamped():
    sweep = DimmerSweep(start_pct=250, direction_up=False, min_pct=10, max_pct=90, step_pct=40)
    assert drain(sweep) == [50, 10]


def test_sweep_step_larger_than_range():
    sweep = DimmerSweep(start_pct=40, direction_up=True, min_pct=30, max_pct=60, step_pct=99)
    assert drain(sweep) == [60]


def test_choose_direction_rules():
    # Off lights always ramp up.
    assert choose_dim_direction(False, None, last_up=False, min_pct=1, max_pct=100) is True
    # Parked at a bound: sweep away from it.
    assert choose_dim_direction(True, 100, last_up=True, min_pct=1, max_pct=100) is False
    assert choose_dim_direction(True, 1, last_up=False, min_pct=1, max_pct=100) is True
    # Lit and mid-range: first hold dims down, then alternates.
    assert choose_dim_direction(True, 50, last_up=None, min_pct=1, max_pct=100) is False
    assert choose_dim_direction(True, 50, last_up=False, min_pct=1, max_pct=100) is True
    assert choose_dim_direction(True, 50, last_up=True, min_pct=1, max_pct=100) is False


def test_breaker_recovers_after_cooldown_and_link_works_again():
    clock = FakeClock()
    core = armed_core(clock, key_on=False, entity_on=False)

    # Trip the breaker with an adversarial burst.
    state = True
    for round_number in range(40):
        if round_number % 2 == 0:
            core.on_entity_state(state)
        else:
            core.on_key_status(not state)
            state = not state
    assert core.breaker.is_open

    clock.advance(31)
    assert not core.breaker.is_open
    # After a clean re-seed, the link works normally again.
    core.seed(key_on=False, entity_on=False)
    clock.advance(ToggleLinkCore.WARMUP_SECONDS + 1)
    assert core.on_key_status(False) == RECORDED  # poll baseline first
    assert core.on_key_status(True) == SYNC_ENTITY
