"""Single-socket discipline tests.

The real vBox accepts only ONE host socket at a time. These tests enforce
that the client never holds two sockets simultaneously (an overlapping or
leaked socket would occupy the device's only slot and lock everyone out),
recovers once a stale slot frees up, and that config-flow validation opens
a short-lived connection that is always closed promptly.
"""

import asyncio
import time

import pytest

from vitrea_integration.vbox_connection import VBoxConnection
from vitrea_integration.vbox_controller import VBoxController

from fake_vbox import FakeVBox


async def wait_until(predicate, timeout: float = 5.0, interval: float = 0.01):
    async def _poll():
        while not predicate():
            await asyncio.sleep(interval)

    await asyncio.wait_for(_poll(), timeout)


async def noop_response(frame: bytes) -> None:
    pass


def make_connection(server: FakeVBox) -> VBoxConnection:
    return VBoxConnection(
        ip=server.host,
        port=server.port,
        response_callback=noop_response,
        event_beat_seconds=0.02,
        keep_alive_interval=0.2,
        rx_timeout=1.0,
        reconnect_base_delay=0.05,
        reconnect_max_delay=0.1,
        connect_retry_delay=0.05,
    )


@pytest.fixture
async def vbox():
    server = FakeVBox(single_connection=True)
    await server.start()
    yield server
    await server.stop()


def _dump_state(vbox, connection, cycle, expected):
    def task_state(task):
        if task is None:
            return "none"
        return "done" if task.done() else "running"

    return (
        f"cycle={cycle} expected>={expected} "
        f"server(connections={vbox.connections}, active={vbox.active_connections}, "
        f"rejected={vbox.rejected}, max_concurrent={vbox.max_concurrent}) "
        f"client(connected={connection.connected}, "
        f"reconnecting={connection.reconnecting}, enabled={connection.enabled}, "
        f"error_reason={connection.error_reason!r}, "
        f"reader={task_state(connection._reader_task)}, "
        f"writer={task_state(connection._writer_task)}, "
        f"monitor={task_state(connection._monitor_task)})"
    )


async def test_no_overlapping_sockets_across_reconnect_storm(vbox):
    connection = make_connection(vbox)
    try:
        await connection.connect()
        # Wait for the server-side handler to register the connection:
        # the client's `connected` flips at TCP-accept time, which can
        # precede the handler task running (drop_client would miss it).
        await wait_until(lambda: vbox.active_connections == 1)

        for cycle in range(1, 5):
            await vbox.drop_client()
            expected = 1 + cycle
            try:
                await wait_until(
                    lambda: vbox.connections >= expected and connection.connected,
                    timeout=10,
                )
            except asyncio.TimeoutError:
                raise AssertionError(
                    "reconnect stalled: " + _dump_state(vbox, connection, cycle, expected)
                ) from None

        assert vbox.max_concurrent == 1, (
            "client held two sockets simultaneously — the real vBox would "
            "have locked out one of them"
        )
    finally:
        await connection.close()


async def test_recovers_after_stale_slot_frees(vbox):
    """Simulates the vBox holding a dead session until its own 40s timeout."""
    connection = make_connection(vbox)
    try:
        await connection.connect()
        await wait_until(lambda: vbox.active_connections == 1)

        vbox.reject_connections = True
        await vbox.drop_client()
        await asyncio.sleep(1.0)  # client cycles against the held slot

        vbox.reject_connections = False
        await wait_until(lambda: connection.connected, timeout=10)
        assert vbox.max_concurrent == 1
    finally:
        await connection.close()


async def test_validation_reports_version_and_frees_socket(vbox):
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=2.0
    )
    assert result["supported"] is True
    assert result["version"] == "9.50"
    assert result["supports_led_commands"] is True
    assert result["reason"] == ""
    # The vBox has one slot: validation must release it immediately.
    await wait_until(lambda: vbox.active_connections == 0)


async def test_validation_tolerates_statuses_and_missing_first_ack(vbox):
    """Observed live on firmware 9.50: unsolicited status frames arrive
    before the auth ack, and the first P:VITREA is not always acked —
    validation must scan frames and retry the auth."""
    vbox.unsolicited_on_connect = b"S:N012:3:F\r\nS:N012:5:R\r\n"
    vbox.skip_first_auth_ack = True
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=1.0
    )
    assert result["supported"] is True
    assert result["version"] == "9.50"
    await wait_until(lambda: vbox.active_connections == 0)


async def test_validation_auth_failure(vbox):
    vbox.auth_reply = b"E:N001:1:001\r\n"
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=0.5
    )
    assert result["supported"] is False
    assert result["reason"] == "auth_failed"
    await wait_until(lambda: vbox.active_connections == 0)


async def test_validation_times_out_quickly_on_silent_server(vbox):
    vbox.respond_to_auth = False
    started = time.monotonic()
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=0.4
    )
    elapsed = time.monotonic() - started

    assert result["supported"] is False
    assert result["reason"] == "connection_error"
    assert elapsed < 3, "validation must fail fast, not hang holding the slot"
    await wait_until(lambda: vbox.active_connections == 0)
