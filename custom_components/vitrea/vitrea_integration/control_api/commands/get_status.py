from .base import Command

class GetFullStatusCommand(Command):
    TEMPLATE = "H:NALL:G\r\n"

    def __init__(self):
        pass

    def serialize(self):
        return self.TEMPLATE.encode()
    
    def validate(self):
        pass

class GetNodeStatusCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:G\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        
class GetOutputStatusCommand(Command):
    TEMPLATE = "H:O{output_id:03d}:G\r\n"

    def __init__(self, output_id):
        self.output_id = output_id

    def serialize(self):
        return self.TEMPLATE.format(
            output_id=self.output_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.output_id, int) or not 0 <= self.output_id <= 999:
            raise ValueError("Output ID must be an integer between 0 and 999.")

class GetThermostatStatusCommand(Command):
    TEMPLATE = "H:A{node_id:03d}:G\r\n"

    def __init__(self, node_id):
        self.node_id = node_id

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")

class GetInputStatusCommand(Command):
    TEMPLATE = "H:I{input_id:03d}:G\r\n"

    def __init__(self, input_id):
        self.input_id = input_id

    def serialize(self):
        return self.TEMPLATE.format(
            input_id=self.input_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.input_id, int) or not 0 <= self.input_id <= 999:
            raise ValueError("Input ID must be an integer between 0 and 999.")

class GetKeyStatusCommand(Command):
    TEMPLATE = "H:N{node_id:03d}:G:{key_id:01d}\r\n"

    def __init__(self, node_id, key_id):
        self.node_id = node_id
        self.key_id = key_id

    def serialize(self):
        return self.TEMPLATE.format(
            node_id=self.node_id,
            key_id=self.key_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.node_id, int) or not 0 <= self.node_id <= 999:
            raise ValueError("Node ID must be an integer between 0 and 999.")
        if not isinstance(self.key_id, int) or not 0 <= self.key_id <= 9:
            raise ValueError("Key ID must be an integer between 0 and 9.")

class GetOccupancyStatusCommand(Command):
    TEMPLATE = "H:C:G\r\n"

    def __init__(self):
        pass

    def serialize(self):
        return self.TEMPLATE.encode()
    
    def validate(self):
        pass

