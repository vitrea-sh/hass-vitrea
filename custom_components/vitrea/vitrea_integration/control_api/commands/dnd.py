from .base import Command
from enum import Enum

class DNDStatus(Enum):
    OFF = 0
    DND = 1
    MUR = 2


class DNDSetStatus(Command):
    TEMPLATE = "H:N{node_id:03d}:1:d:{status}\r\n"

    def __init__(self, node_id, status: DNDStatus):
        self.node_id = node_id
        self.status = status

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id, status=self.status.value
        ).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.status, DNDStatus):
            raise ValueError("Status must be an instance of DNDStatus.")
