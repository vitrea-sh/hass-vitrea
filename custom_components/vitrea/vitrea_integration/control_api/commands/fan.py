from .base import Command
from enum import Enum

"""
TODO - This logic is not yet implemented in the VBox API.
"""

class FanSpeed(Enum):
        OFF = 0
        LOW = 1
        MEDIUM = 2
        HIGH = 3
        MAX = 4


class FanSetSpeedCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:S:{speed:01d}\r\n"
    
    def __init__(self, node_id, speed: FanSpeed):
        self.node_id = node_id
        self.speed = speed
    
    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id,
            speed=self.speed.value
        ).encode()
    
    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.speed, FanSpeed):
            raise ValueError("Speed must be an instance of FanSpeed.")

class FanOffCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:S:0\r\n"
    
    def __init__(self, node_id):
        self.node_id = node_id
    
    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")