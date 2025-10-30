from .base import Command


class DimmerIntensityCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:D:{duration:03d}:{intensity:03d}\r\n"

    def __init__(self, node_id, key_id, intensity, duration=0):
        self.node_id = node_id
        self.key_id = key_id
        self.duration = duration
        self.intensity = intensity

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id,
            key_id=self.key_id,
            duration=self.duration,
            intensity=self.intensity,
        ).encode()

    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")
        if not isinstance(self.duration, int) or not 0 <= self.duration <= 120:
            raise ValueError("Duration must be an integer between 0 and 120.")
        if not isinstance(self.intensity, int) or not 0 <= self.intensity <= 100:
            raise ValueError("Intensity must be an integer between 0 and 100.")


class DimmerUpCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:D:100\r\n"

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


class DimmerDownCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:D:000\r\n"

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


class DimmerStopCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:D:000:255\r\n"

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


class DimmerRecallLastCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:{key_id:01d}:D:{duration:03d}:254\r\n"

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
