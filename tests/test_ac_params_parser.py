"""AC parameters parsing: firmware layout deviations and load resilience.

Seen in the field on firmware 9.50: adding a single AC to the vBox
database took the whole integration down. That firmware answers Get A/C
Parameters WITHOUT the thermostat_type byte the spec (rev 2.108)
promises — AC_no, room_no, name_len, name — so the parser raised
"Not a digit", the AC never loaded, the DB completeness check saw
ACs 0/1 forever, and setup retried into ConfigEntryNotReady. Two guarantees
are proven here:

1. The parser accepts all three observed/spec layouts (ASCII type,
   binary type, and no type byte at all — warned, assumed Type 1).
2. An AC record that still fails to parse degrades to a warning and a
   missing climate entity, never a wedged database load.
"""

import asyncio
import logging

import pytest

from vitrea_integration.parameter_api.v3.reader import VitreaDatabaseReader
from vitrea_integration.parameter_api.v3.responses.acs import ACParamsParser
from vitrea_integration.utils.enums import AirConditionerType

# The frame as captured from the controller: AC 1, room 1, name "מזגן",
# valid checksum, no thermostat_type byte.
INCIDENT_FRAME = bytes.fromhex("5654483c08000e0001000108de05d605d205df05c7")

NAME = "מזגן"
NAME_BYTES = NAME.encode("utf-16-le")


def build_frame(payload: bytes, cmd: int = 8) -> bytes:
    """Assemble VTH< + C# + len(2, includes checksum) + payload + cs."""
    body = b"VTH<" + bytes([cmd]) + (len(payload) + 1).to_bytes(2, "big") + payload
    return body + bytes([sum(body) % 256])


class FakeSendCallback:
    def __init__(self):
        self.queued_next = 0

    async def queue_next_ac(self):
        self.queued_next += 1


def test_frame_builder_reproduces_incident_frame():
    payload = bytes([0, 1, 0, 1, len(NAME_BYTES)]) + NAME_BYTES
    assert build_frame(payload) == INCIDENT_FRAME


async def _parse(frame: bytes):
    callback = FakeSendCallback()
    parser = ACParamsParser(raw_data=frame, send_callback=callback)
    result = await parser.parse_response()
    return result, callback


async def test_typeless_layout_warns_and_assumes_type_1(caplog):
    """The incident frame parses: warning produced, Type 1 assumed."""
    with caplog.at_level(logging.WARNING):
        result, callback = await _parse(INCIDENT_FRAME)
    assert len(result) == 1
    ac = result[0]
    assert ac.id == 1
    assert ac.room_id == 1
    assert ac.name == NAME
    assert ac.type == AirConditionerType.TYPE_1
    assert callback.queued_next == 1
    assert "assuming Type 1" in caplog.text


async def test_spec_ascii_type_layout():
    payload = bytes([0, 2]) + b"3" + bytes([0, 5, len(NAME_BYTES)]) + NAME_BYTES
    result, _ = await _parse(build_frame(payload))
    ac = result[0]
    assert ac.id == 2
    assert ac.room_id == 5
    assert ac.name == NAME
    assert ac.type == AirConditionerType.TYPE_3


async def test_binary_type_layout():
    payload = bytes([0, 2, 4, 0, 5, len(NAME_BYTES)]) + NAME_BYTES
    result, _ = await _parse(build_frame(payload))
    ac = result[0]
    assert ac.type == AirConditionerType.TMSF
    assert ac.room_id == 5
    assert ac.name == NAME


async def test_unrecognizable_layout_raises():
    with pytest.raises(ValueError):
        await _parse(build_frame(b"\xff" * 6))


# --- reader resilience ---


async def _feed_reader(frame: bytes):
    async def writer(command):
        pass

    reader = VitreaDatabaseReader(write=writer)
    reader.db.no_of_acs = 1
    reader.pending_request = asyncio.get_running_loop().create_future()
    reader._pending_command_number = frame[4]
    future = reader.pending_request
    await reader.feed(frame)
    return reader, future


async def test_bad_ac_record_does_not_wedge_db_load(caplog):
    """A still-unparseable AC record degrades: count adjusted, no raise."""
    with caplog.at_level(logging.WARNING):
        reader, future = await _feed_reader(build_frame(b"\xff" * 6))
    assert future.done() and future.result() == []
    assert reader.db.no_of_acs == 0
    assert reader.db.is_acs_loaded()
    assert "Skipping unparseable AC record" in caplog.text


async def test_incident_frame_loads_ac_through_reader():
    """End to end through feed(): the incident frame lands in the DB."""
    reader, future = await _feed_reader(INCIDENT_FRAME)
    assert future.done()
    assert len(reader.db.air_conditioners) == 1
    assert reader.db.is_acs_loaded()
    ac = next(iter(reader.db.air_conditioners))
    assert ac.name == NAME
    assert ac.type == AirConditionerType.TYPE_1
