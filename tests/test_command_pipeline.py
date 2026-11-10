"""Tests for command delivery, pacing, notification dedupe, DB-read
correlation, and satellite event dispatch."""

import asyncio

import pytest

from vitrea_integration.models.satellite import Satellite
from vitrea_integration.parameter_api.v3.commands.scenarios import GetScenarioNumbers
from vitrea_integration.parameter_api.v3.reader import VitreaDatabaseReader

from fake_vbox import FakeVBox
from test_vbox_connection import make_connection, wait_until

COMMAND = b"H:N001:1:T\r\n"


@pytest.fixture
async def vbox():
    server = FakeVBox()
    await server.start()
    yield server
    await server.stop()


# --- Connection-state notifications fire once per transition ---


async def test_connect_notifies_connected_exactly_once(vbox):
    connection, recorder = make_connection(vbox)
    try:
        await connection.connect()
        await wait_until(lambda: vbox.active_connections == 1)
        await asyncio.sleep(0.1)
        assert recorder.states == [True]
    finally:
        await connection.close()


async def test_reconnect_notifies_each_transition_once(vbox):
    connection, recorder = make_connection(vbox)
    try:
        await connection.connect()
        await wait_until(lambda: vbox.active_connections == 1)
        await vbox.drop_client()
        await wait_until(lambda: vbox.connections >= 2 and connection.connected)
        await asyncio.sleep(0.1)
        assert recorder.states == [True, False, True]
    finally:
        await connection.close()


# --- Command queueing across disconnects ---


async def test_command_queued_while_disconnected_is_delivered(vbox):
    connection, _ = make_connection(vbox)
    try:
        # Never explicitly connected: send() must queue the command,
        # trigger a reconnect, and deliver once the link is up.
        await connection.send(COMMAND)
        await wait_until(lambda: COMMAND in vbox.commands, timeout=10)
    finally:
        await connection.close()


async def test_stale_queued_command_is_dropped(vbox):
    connection, _ = make_connection(vbox, max_command_age=0.1)
    try:
        await vbox.stop_listening()
        await connection.send(COMMAND)
        await asyncio.sleep(0.4)  # command goes stale during the outage
        await vbox.start()
        await wait_until(lambda: connection.connected, timeout=10)
        await asyncio.sleep(0.2)
        assert not any(c.startswith(b"H:") for c in vbox.commands), (
            "a stale command from before the outage must not replay"
        )
    finally:
        await connection.close()


# --- Writer pacing (spec: next command only after an answer) ---


async def _send_burst_and_measure(vbox, connection):
    await connection.connect()
    await asyncio.wait_for(vbox.auth_received.wait(), 5)
    await asyncio.sleep(0.1)  # let the auth ack land before the burst
    burst = [b"H:N001:1:T\r\n", b"H:N001:2:T\r\n", b"H:N001:3:T\r\n"]
    for command in burst:
        await connection.send(command)
    await wait_until(
        lambda: sum(1 for c in vbox.commands if c.startswith(b"H:")) >= 3,
        timeout=10,
    )
    times = [t for c, t in vbox.command_times if c.startswith(b"H:")]
    return times[-1] - times[0]


async def test_writer_paces_burst_when_acks_missing(vbox):
    connection, _ = make_connection(
        vbox, keep_alive_interval=60.0, rx_timeout=5.0, command_ack_timeout=0.3
    )
    try:
        spread = await _send_burst_and_measure(vbox, connection)
        assert spread >= 0.5, f"burst not paced: {spread:.3f}s for 3 commands"
    finally:
        await connection.close()


async def test_writer_flows_fast_when_acks_arrive(vbox):
    vbox.ack_commands = True
    connection, _ = make_connection(
        vbox, keep_alive_interval=60.0, rx_timeout=5.0, command_ack_timeout=0.3
    )
    try:
        spread = await _send_burst_and_measure(vbox, connection)
        assert spread < 0.3, f"acked burst should not be throttled: {spread:.3f}s"
    finally:
        await connection.close()


async def test_status_reply_unblocks_pacing(vbox):
    """Regression: single-key status requests (H:Nxxx:G:K) are answered
    with the status frame and NO OK — seen live as a ~1s/command drain
    that expired ~27 initial-state queries past the 10s staleness cap."""
    vbox.status_reply_to_get = True
    connection, _ = make_connection(
        vbox, keep_alive_interval=60.0, rx_timeout=5.0, command_ack_timeout=0.5
    )
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.auth_received.wait(), 5)
        await asyncio.sleep(0.1)
        burst = [f"H:N{n:03d}:G:1\r\n".encode() for n in range(1, 11)]
        for command in burst:
            await connection.send(command)
        await wait_until(
            lambda: sum(1 for c in vbox.commands if c.startswith(b"H:N")) >= 10,
            timeout=10,
        )
        times = [t for c, t in vbox.command_times if c.startswith(b"H:N")]
        spread = times[-1] - times[0]
        assert spread < 1.0, (
            f"10 status queries took {spread:.2f}s — status replies are not "
            "unblocking the pacing wait"
        )
    finally:
        await connection.close()


# --- DB-read request/response correlation ---


def make_param_response(cmd_no: int, payload: bytes) -> bytes:
    body = b"VTH<" + bytes([cmd_no]) + (len(payload) + 1).to_bytes(2, "big") + payload
    return body + bytes([sum(body) % 256])


async def test_db_feed_ignores_mismatched_command_number():
    sent = []

    async def write(data: bytes) -> bool:
        sent.append(data)
        return True

    reader = VitreaDatabaseReader(write=write)
    request = asyncio.create_task(
        reader.send_command(GetScenarioNumbers(), timeout=2.0)
    )
    await asyncio.sleep(0.05)
    assert sent, "command was not written"
    assert not request.done()

    # A late reply for a DIFFERENT command (AC numbers, C#7) must not
    # resolve the pending scenario-numbers (C#9) request.
    await reader.feed(make_param_response(7, b"\x00"))
    await asyncio.sleep(0.05)
    assert not request.done(), "future resolved with a mismatched command's data"

    await reader.feed(make_param_response(9, b"\x00"))
    result = await asyncio.wait_for(request, 2)
    assert result.get("no_of_scenarios") == 0


# --- Satellite events: every press dispatches, even rapid double-press ---


class StubConnection:
    async def send(self, command: bytes) -> bool:
        return True


class StubController:
    def __init__(self) -> None:
        self.connection = StubConnection()


async def test_satellite_events_fire_for_rapid_double_press():
    satellite = Satellite(
        node_id=1,
        key_id=1,
        key_name="Button",
        room_name="Room",
        controller=StubController(),
    )
    events = []
    satellite.register_event_callback(events.append)

    await satellite.update_state({"sub_type": "satellite_key_short"})
    await satellite.update_state({"sub_type": "satellite_key_short"})

    assert events == ["Short", "Short"], (
        "both presses must dispatch as events even within the 1s state window"
    )

    satellite.remove_event_callback(events.append)
