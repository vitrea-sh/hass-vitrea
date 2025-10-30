# parsers/input_status_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class InputStatusResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses an input status response from the VBox.

        Expected format: S:Ixxx:S:PP...P <CR><LF>
        Where:
        - Ixxx is the input number.
        - S is a fixed character indicating status.
        - PP...P is the parameter of the command which may vary based on the input type.
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the input status.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if len(parts) != 3 or not parts[1].startswith('I'):
                logger.error(f"Unexpected format for input status response: {response}")
                raise ValueError("Unexpected format for input status response")

            input_id = parts[1][2:]  # Remove the 'S:I' prefix to get the input ID
            status = parts[2]
            if status == 'C':
                status = True
            elif status == 'O':
                status = False
            else:
                logger.error(f"Unexpected status value in input status response: {response}")
                raise ValueError("Unexpected status value in input status response")

            input_status = {
                'type': 'input_status',
                'input_id': input_id,
                'status': status,
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return input_status

        except Exception as e:
            logger.error(f"Error parsing input status response: {response} - Error: {e}")
            raise

