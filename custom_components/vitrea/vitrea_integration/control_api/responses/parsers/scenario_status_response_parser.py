# parsers/scenario_status_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ScenarioStatusResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses a scenario status response from the VBox.

        Expected format: S:Rxxxx:status <CR><LF>
        Where:
        - Rxxxx is the scenario ID number.
        - status is the execution status (OK or ERROR).
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the scenario execution status.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if len(parts) != 3:
                raise ValueError("Incomplete scenario status response")

            scenario_id = int(parts[1][1:])
            execution_status = parts[2] == 'OK'

            scenario_status = {
                'type': 'scenario_status',
                'scenario_id': scenario_id,
                'executed': execution_status,
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return scenario_status

        except Exception as e:
            logger.error(f"Error parsing scenario status response: {response} - Error: {e}")
            raise

