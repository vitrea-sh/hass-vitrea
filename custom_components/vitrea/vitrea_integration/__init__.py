"""Vitrea Integration for Home Assistant.

The Integration works over TCP to the Host Port of the Vitrea Gateway.

This integration allows you to control Vitrea devices.
"""

import asyncio
import logging
import socket
from .vbox_controller import VBoxController

_LOGGER = logging.getLogger(__name__)

COMMANDS = {"ascii": {"auth": {"cmd": b"P:VITREA\r\n", "res": b"S:PSW:OK\r\n"}}}


async def authenticate_vitrea_device(host: str, port: int) -> bool:
    """Authenticate to the Vitrea Gateway."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((host, port))
            s.settimeout(5)
            s.sendall(COMMANDS.get("ascii", {}).get("auth", {}).get("cmd"))
            data = s.recv(1024)
            if data == b"S:PSW:OK\r\n":
                s.close()
                return True
    except (ConnectionError, TimeoutError) as e:
        _LOGGER.warning("Could not init Vitrea due to %s", e)
    return False


async def validate_controller_availability(ip: str, port: int) -> dict:
    """Check if the Vitrea Gateway is available and supported."""
    return await VBoxController.validate_controller_availability(ip, port)
