# parsers/output_status_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class OutputStatusResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses an output status response from the VBox.

        Expected format: S:Oxxx:S:PP...P <CR><LF>
        Where:
        - Oxxx is the output number.
        - S is a fixed character indicating status.
        - PP...P are the parameters of the command which may vary based on the output type.
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the output status.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if len(parts) < 4 or not parts[0].startswith('S:O'):
                logger.error(f"Unexpected format for output status response: {response}")
                raise ValueError("Unexpected format for output status response")

            output_id = parts[0][2:]  # Remove the 'S:O' prefix to get the output ID
            status = parts[2]
            parameters = parts[3]

            output_status = {
                'type': 'output_status',
                'output_id': output_id,
                'status': status,
                'parameters': parameters,
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return output_status

        except Exception as e:
            logger.error(f"Error parsing output status response: {response} - Error: {e}")
            raise

