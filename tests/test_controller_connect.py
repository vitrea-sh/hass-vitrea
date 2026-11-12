"""Full controller lifecycle against the fake vBox: DB read over the
socket, and the ordering of the bulk status sync (H:NALL:G).

The bulk sync must NOT happen inside controller.connect() — at that point
the consumer's devices don't exist yet and the status frames would land
nowhere. The consumer (hub) requests it explicitly after registering
devices.
"""


import pytest

from vitrea_integration.vbox_controller import VBoxController

from fake_vbox import FakeVBox
from test_command_pipeline import make_param_response
from test_vbox_connection import wait_until

# Zero-count replies for every "get numbers" command: floors(1),
# rooms(3), keypads(5, two-byte count), ACs(7), scenarios(9).
ZERO_DB_REPLIES = {
    1: make_param_response(1, b"\x00"),
    3: make_param_response(3, b"\x00"),
    5: make_param_response(5, b"\x00\x00"),
    7: make_param_response(7, b"\x00"),
    9: make_param_response(9, b"\x00"),
}


@pytest.fixture
async def vbox():
    server = FakeVBox()
    server.param_replies = dict(ZERO_DB_REPLIES)
    await server.start()
    yield server
    await server.stop()


async def test_connect_reads_db_without_premature_status_sync(vbox):
    controller = VBoxController(ip=vbox.host, port=vbox.port)
    try:
        connected = await controller.connect(watchdog=False)
        assert connected
        assert controller.database is not None
        assert controller.database.is_loaded()

        assert b"H:NALL:G\r\n" not in vbox.commands, (
            "bulk status sync must be requested by the consumer after its "
            "devices are registered, not inside controller.connect()"
        )

        # The hub requests it explicitly once devices exist:
        await controller.update_state()
        await wait_until(lambda: b"H:NALL:G\r\n" in vbox.commands)
    finally:
        await controller.close()
