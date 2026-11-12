"""Regression tests for the state-pipeline fixes.

Covers: error-frame parsing (spec E:Nxxx:K:PPP), callback fan-out isolation,
stuck blind movement flags, non-blocking satellite Short reset, and guarded
status updates on malformed frames.
"""

import asyncio
import time

from vitrea_integration.control_api.responses import parse_response
from vitrea_integration.models.blind import Blind
from vitrea_integration.models.light import Dimmer
from vitrea_integration.models.satellite import Satellite
from vitrea_integration.models.toggle import Toggle


class StubConnection:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.send_result = True

    async def send(self, command: bytes) -> bool:
        self.sent.append(command)
        return self.send_result


class StubController:
    def __init__(self) -> None:
        self.connection = StubConnection()


def make_device(cls, **kwargs):
    return cls(
        node_id=1,
        key_id=1,
        key_name="Test",
        room_name="Room",
        controller=StubController(),
        **kwargs,
    )


# --- Error frames (spec section 6: E:Nxxx:K:PPP) ---


def test_error_frame_parses_with_spec_code_mapping():
    result = parse_response(b"E:N001:1:003\r\n")
    assert result["type"] == "error"
    assert result["node_id"] == 1
    assert result["key"] == "1"
    assert result["error_code"] == 3
    assert result["description"] == "Wrong Node Number"


def test_error_frame_all_spec_codes():
    descriptions = {
        1: "Wrong Command",
        2: "Wrong Input",
        3: "Wrong Node Number",
        4: "Wrong Key Number",
        5: "Node not found",
        6: "Wrong Scenario",
    }
    for code, description in descriptions.items():
        result = parse_response(f"E:N010:2:{code:03d}")
        assert result["error_code"] == code
        assert result["description"] == description


def test_error_frame_unknown_shape_does_not_crash():
    result = parse_response("E:garbage:frame")
    assert result["type"] == "error"
    assert result["error_code"] is None


# --- Callback fan-out isolation ---


async def test_one_failing_callback_does_not_block_others():
    toggle = make_device(Toggle)
    calls = []

    def bad_callback():
        raise RuntimeError("entity went away")

    toggle.register_callback(bad_callback)
    toggle.register_callback(lambda: calls.append("a"))
    toggle.register_callback(lambda: calls.append("b"))

    await toggle.update_state({"status": True})

    assert sorted(calls) == ["a", "b"]
    assert toggle.is_on is True


# --- Toggle guarded updates ---


async def test_toggle_missing_status_keeps_previous_state():
    toggle = make_device(Toggle, initial_state=True)
    await toggle.update_state({"parameters": "005"})
    assert toggle.is_on is True
    assert toggle.countdown_minutes == 5


async def test_toggle_invalid_countdown_does_not_crash():
    toggle = make_device(Toggle)
    await toggle.update_state({"status": True, "parameters": "abc"})
    assert toggle.is_on is True


# --- Dimmer guarded updates ---


async def test_dimmer_status_without_intensity_is_ignored():
    dimmer = make_device(Dimmer, initial_intensity=42)
    await dimmer.update_state({"status": True, "parameters": None})
    assert dimmer.intensity == 42


# --- Blind movement flags ---


async def test_blind_flags_clear_on_same_position_report():
    blind = make_device(Blind, initial_location=0)
    await blind.set_location(100)
    assert blind.is_opening
    # Controller reports back the unchanged position (e.g. blocked blind):
    # the report itself means execution finished, so flags must clear.
    await blind.update_state({"parameters": "000"})
    assert not blind.is_opening
    assert not blind.is_closing


async def test_blind_flags_expire_when_no_report_arrives():
    blind = make_device(Blind, initial_location=0)
    blind.MOVEMENT_TIMEOUT = 0.05
    await blind.set_location(100)
    assert blind.is_opening
    await asyncio.sleep(0.1)
    assert not blind.is_opening


async def test_blind_no_flags_when_send_fails():
    blind = make_device(Blind, initial_location=0)
    blind.controller.connection.send_result = False
    await blind.set_location(100)
    assert not blind.is_opening


async def test_blind_invalid_status_does_not_crash():
    blind = make_device(Blind, initial_location=30)
    await blind.update_state({"parameters": None})
    await blind.update_state({"parameters": "abc"})
    assert blind.location == 30


# --- Satellite non-blocking Short reset ---


async def test_satellite_short_reset_is_nonblocking():
    satellite = make_device(Satellite)
    started = time.monotonic()
    await satellite.update_state({"sub_type": "satellite_key_short"})
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, "update_state must not sleep inline"
    assert satellite.native_value == "Short"
    await asyncio.sleep(1.2)
    assert satellite.native_value == "Release"


async def test_satellite_missing_sub_type_is_ignored():
    satellite = make_device(Satellite)
    await satellite.update_state({"status": None})
    assert satellite.native_value == "Release"
