"""Vitrea Integration for Home Assistant.

The Integration works over TCP to the Host Port of the Vitrea Gateway.

This integration allows you to control Vitrea devices.

Note: the vBox accepts a single host socket at a time, so all communication
must go through one VBoxController/VBoxConnection instance; short-lived
validation connections must be closed promptly.
"""

from .vbox_controller import VBoxController


async def validate_controller_availability(ip: str, port: int) -> dict:
    """Check if the Vitrea Gateway is available and supported."""
    return await VBoxController.validate_controller_availability(ip, port)


def supports_v95_features(version: str) -> bool:
    """Return True when the firmware has the 9.5 feature set.

    Covers satellite LED indicator control (L command) and Room-On keys.
    Version strings look like "9.50"; major 0 marks development firmware,
    which is assumed to have everything.
    """
    try:
        major, minor = (int(part) for part in version.split(".", 1))
    except (AttributeError, ValueError):
        return False
    return major == 0 or (major, minor) >= (9, 50)
