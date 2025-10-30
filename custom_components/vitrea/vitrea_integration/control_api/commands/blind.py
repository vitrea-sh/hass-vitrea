"""
    # Blind to location 'xxx'
    "blind_location": "H:N{node_id:03d}:{key_id:01d}:B:{location:03d}\r\n",
    # Blind up to maximum
    "blind_up": "H:N{node_id:03d}:{key_id:01d}:B:100\r\n",
    # Blind down – Closed position
    "blind_down": "H:N{node_id:03d}:{key_id:01d}:B:000\r\n",
    # Blind stop
    "blind_stop": "H:N{node_id:03d}:{key_id:01d}:B:255\r\n",
"""

from .base import Command


class BlindLocationCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:B:{location:03d}\r\n"

    def __init__(self, node_id, key_id, location):
        self.node_id = node_id
        self.key_id = key_id
        self.location = location

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id, key_id=self.key_id, location=self.location
        ).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")
        if not isinstance(self.location, int) or not 0 <= self.location <= 100:
            raise ValueError("Location must be an integer between 0 and 100.")


class BlindUpCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:B:100\r\n"

    def __init__(self, node_id, key_id):
        self.node_id = node_id
        self.key_id = key_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id, key_id=self.key_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")


class BlindDownCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:B:000\r\n"

    def __init__(self, node_id, key_id):
        self.node_id = node_id
        self.key_id = key_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id, key_id=self.key_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")


class BlindStopCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:B:255\r\n"

    def __init__(self, node_id, key_id):
        self.node_id = node_id
        self.key_id = key_id

    def serialize(self):
        return self.TEMPLATE.format(node_id=self.node_id, key_id=self.key_id).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")
