from .base import Command

class ScenarioCommand(Command):
    TEMPLATE = "H:R{scenario_id:04d}\r\n"

    def __init__(self, scenario_id):
        self.scenario_id = scenario_id

    def serialize(self):
        return self.TEMPLATE.format(scenario_id=self.scenario_id).encode()

    def validate(self):
        if not isinstance(self.scenario_id, int) or not 0 <= self.scenario_id <= 9999:
            raise ValueError("Scenario ID must be an integer between 0 and 9999.")