"""Regression tests for the VBoxConnection stability fixes.

Each test targets a failure mode of the real protocol (spec rev 2.108):
TCP fragmentation and coalescing, controller-side disconnects, half-open
(silent) sockets, and outages longer than the old 10-attempt reconnect
limit.
"""

import asyncio

import pytest

from vitrea_integration.vbox_connection import VBoxConnection

from fake_vbox import AUTH_ACK, FakeVBox


async def wait_until(predicate, timeout: float = 5.0, interval: float = 0.01):
    """Poll until predicate() is true or fail the test after timeout."""

    async def _poll():
        while not predicate():
            await asyncio.sleep(interval)

    await asyncio.wait_for(_poll(), timeout)


class Recorder:
    """Collects frames and connection-state transitions from VBoxConnection."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.states: list[bool] = []

    async def on_response(self, frame: bytes) -> None:
        self.frames.append(frame)

    async def on_connection(self, state: bool) -> None:
        self.states.append(state)


def make_connection(server: FakeVBox, **overrides) -> tuple[VBoxConnection, Recorder]:
    """Build a VBoxConnection with test-friendly (fast) timings."""
    recorder = Recorder()
    settings = dict(
        event_beat_seconds=0.02,
        keep_alive_interval=0.2,
        rx_timeout=1.0,
        reconnect_base_delay=0.02,
        reconnect_max_delay=0.05,
        connect_retry_delay=0.02,
    )
    settings.update(overrides)
    connection = VBoxConnection(
        ip=server.host,
        port=server.port,
        response_callback=recorder.on_response,
        connection_callback=recorder.on_connection,
        **settings,
    )
    return connection, recorder


@pytest.fixture
async def vbox():
    server = FakeVBox()
    await server.start()
    yield server
    await server.stop()


async def test_connect_authenticates_and_receives_ack(vbox):
    connection, recorder = make_connection(vbox)
    try:
        assert await connection.connect()
        await asyncio.wait_for(vbox.auth_received.wait(), 5)
        await wait_until(lambda: AUTH_ACK in recorder.frames)
        assert connection.connected
    finally:
        await connection.close()


async def test_fragmented_ascii_frame_is_reassembled(vbox):
    frame = b"S:N001:1:O\r\n"
    # Long keep-alive interval so no S:PSW:OK ack from the server can
    # interleave with the scripted fragments below.
    connection, recorder = make_connection(
        vbox, keep_alive_interval=60.0, rx_timeout=5.0
    )
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.auth_received.wait(), 5)
        await vbox.send_fragmented(frame, chunk_size=1)
        await wait_until(lambda: frame in recorder.frames)
    finally:
        await connection.close()


async def test_fragmented_binary_frame_is_reassembled(vbox):
    payload = b"ABCDE"
    frame = b"VTH<" + bytes([2]) + len(payload).to_bytes(2, "big") + payload
    connection, recorder = make_connection(
        vbox, keep_alive_interval=60.0, rx_timeout=5.0
    )
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.auth_received.wait(), 5)
        # Chunks deliberately split inside the header and the length field.
        for chunk in (frame[:3], frame[3:6], frame[6:9], frame[9:]):
            await vbox.send(chunk)
            await asyncio.sleep(0.05)
        await wait_until(lambda: frame in recorder.frames)
    finally:
        await connection.close()


async def test_coalesced_frames_are_split(vbox):
    first = b"S:N001:1:O\r\n"
    second = b"S:N002:1:F\r\n"
    connection, recorder = make_connection(vbox)
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.client_connected.wait(), 5)
        await vbox.send(first + second)
        await wait_until(
            lambda: first in recorder.frames and second in recorder.frames
        )
    finally:
        await connection.close()


async def test_server_close_triggers_reconnect(vbox):
    connection, recorder = make_connection(vbox)
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.client_connected.wait(), 5)
        await vbox.drop_client()
        await wait_until(lambda: vbox.connections >= 2)
        await wait_until(lambda: connection.connected)
        assert False in recorder.states
    finally:
        await connection.close()


async def test_oversized_binary_length_resets_connection(vbox):
    connection, recorder = make_connection(vbox)
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.client_connected.wait(), 5)
        # Length field claims 8192 bytes: a desynced/garbage frame. The old
        # code would block waiting for data that never comes.
        bogus = b"VTH<" + bytes([2]) + (0x2000).to_bytes(2, "big")
        await vbox.send(bogus)
        await wait_until(lambda: vbox.connections >= 2)
        await wait_until(lambda: connection.connected)
    finally:
        await connection.close()


async def test_silent_connection_is_detected_and_reset(vbox):
    # Server accepts but never sends anything (half-open/zombie socket).
    # Before the fix, last_rx stayed None and the monitor never fired.
    vbox.respond_to_auth = False
    connection, _ = make_connection(vbox, rx_timeout=0.5)
    try:
        await connection.connect()
        await wait_until(lambda: vbox.connections >= 2, timeout=10)
    finally:
        await connection.close()


async def test_reconnect_survives_long_outage(vbox):
    connection, _ = make_connection(vbox)
    try:
        await connection.connect()
        await asyncio.wait_for(vbox.client_connected.wait(), 5)

        await vbox.stop()  # full outage: listener closed, client dropped
        # Each reconnect cycle takes ~0.1-0.2s with the test timings, so this
        # outage spans far more than the 10 attempts the old code gave up at.
        await asyncio.sleep(2.5)

        await vbox.start()  # controller comes back on the same port
        await wait_until(lambda: connection.connected, timeout=10)
        assert vbox.connections >= 2
    finally:
        await connection.close()
