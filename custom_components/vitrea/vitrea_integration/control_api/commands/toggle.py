from .base import Command


class ToggleOnCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:O:{duration:03d}\r\n"

    def __init__(self, node_id, key_id, duration=0):
        self.node_id = node_id
        self.key_id = key_id
        self.duration = duration

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id, key_id=self.key_id, duration=self.duration
        ).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")
        if not isinstance(self.duration, int) or not 0 <= self.duration <= 120:
            raise ValueError("Duration must be an integer between 0 and 120.")


class ToggleOffCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:F\r\n"

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


class ToggleToggleCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:T\r\n"

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
