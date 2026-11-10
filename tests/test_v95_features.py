"""Tests for the firmware-9.5 feature set: version gating, Room-On keys,
and the LED-command gate boundary."""

import pytest

from vitrea_integration import supports_v95_features
from vitrea_integration.models.room_on import RoomOn
from vitrea_integration.utils.enums import KeyTypes
from vitrea_integration.vbox_controller import VBoxController

from fake_vbox import FakeVBox


@pytest.fixture
async def vbox():
    server = FakeVBox()
    await server.start()
    yield server
    await server.stop()


# --- Version gate ---


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("9.50", True),
        ("9.51", True),
        ("10.0", True),
        ("0.1", True),  # development firmware
        ("9.49", False),
        ("9.5", False),  # minor 5 == firmware V:905, below 9.50
        ("8.63", False),
        ("", False),
        ("garbage", False),
        (None, False),
    ],
)
def test_supports_v95_features(version, expected):
    assert supports_v95_features(version) is expected


# --- Room-On model: toggle wire behavior, key type 13 ---


class StubConnection:
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, command: bytes) -> bool:
        self.sent.append(command)
        return True


class StubController:
    def __init__(self) -> None:
        self.connection = StubConnection()


async def test_room_on_behaves_like_toggle():
    room = RoomOn(
        node_id=5,
        key_id=2,
        key_name="Living Room",
        room_name="Ground",
        controller=StubController(),
    )
    assert room.supported_key_types == [KeyTypes.RoomOn.value]

    await room.turn_on()
    assert room.controller.connection.sent == [b"H:N005:2:O:000\r\n"]

    await room.update_state({"status": True})
    assert room.is_on is True

    await room.turn_off()
    assert room.controller.connection.sent[-1] == b"H:N005:2:F\r\n"
    await room.update_state({"status": False})
    assert room.is_on is False


# --- LED-command gate boundary in validation ---


async def test_led_commands_gated_below_9_50(vbox):
    vbox.version_reply = b"V:949\r\n"
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=2.0
    )
    assert result["supported"] is True  # 9.x is supported firmware
    assert result["version"] == "9.49"
    assert result["supports_led_commands"] is False


async def test_led_commands_enabled_at_9_50(vbox):
    result = await VBoxController.validate_controller_availability(
        vbox.host, vbox.port, timeout=2.0
    )
    assert result["version"] == "9.50"
    assert result["supports_led_commands"] is True
