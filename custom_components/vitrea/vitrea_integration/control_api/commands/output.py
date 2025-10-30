"""
TODO - This functionality is not yet implemented in the VBox API.
"""

from .base import Command

class CloseOutputCommand(Command):
    TEMPLATE = "H:O{output_id:03d}:C\r\n"

    def __init__(self, output_id):
        self.output_id = output_id

    def serialize(self):
        return self.TEMPLATE.format(
            output_id=self.output_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.output_id, int) or not 0 <= self.output_id <= 999:
            raise ValueError("Output ID must be an integer between 0 and 999.")
        
class OpenOutputCommand(Command):
    TEMPLATE = "H:O{output_id:03d}:O\r\n"

    def __init__(self, output_id):
        self.output_id = output_id

    def serialize(self):
        return self.TEMPLATE.format(
            output_id=self.output_id
        ).encode()
    
    def validate(self):
        if not isinstance(self.output_id, int) or not 0 <= self.output_id <= 999:
            raise ValueError("Output ID must be an integer between 0 and 999.")