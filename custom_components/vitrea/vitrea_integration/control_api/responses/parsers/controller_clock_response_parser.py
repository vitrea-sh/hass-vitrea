# parsers/controller_clock_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class ControllerClockResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses a controller clock response from the VBox.

        Expected format: T:mm:hh:dd:MM:yyyy:w <CR><LF>
        Where:
        - T indicates a clock response.
        - mm is the minutes.
        - hh is the hours.
        - dd is the day of the month.
        - MM is the month.
        - yyyy is the year.
        - w is the day of the week.
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the controller's clock information.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if not parts[0].startswith('T') or len(parts) != 7:
                logger.error(f"Unexpected format for controller clock response: {response}")
                raise ValueError("Unexpected format for controller clock response")

            clock_info = {
                'type': 'controller_clock',
                'minutes': parts[1],
                'hours': parts[2],
                'day_of_month': parts[3],
                'month': parts[4],
                'year': parts[5],
                'day_of_week': parts[6],
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return clock_info

        except Exception as e:
            logger.error(f"Error parsing controller clock response: {response} - Error: {e}")
            raise

