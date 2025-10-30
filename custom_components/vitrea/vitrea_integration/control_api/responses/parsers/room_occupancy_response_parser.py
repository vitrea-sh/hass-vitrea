# parsers/room_occupancy_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class RoomOccupancyResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses a room occupancy status response from the VBox.

        Expected format: S:C:0/1 <CR><LF>
        Where:
        - 'S:C' indicates a room occupancy status.
        - The following 'S' is a fixed character.
        - '0/1' indicates room not occupied (0) or occupied (1).
        
        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the room occupancy status.
        """
        try:
            response = response.strip()
            parts = response.split(':')
            if len(parts) != 3 or not parts[1] == 'C' or not parts[0] == 'S':
                logger.error(f"Unexpected format for room occupancy response: {response}")
                raise ValueError("Unexpected format for room occupancy response")

            occupancy = parts[2]
            room_occupied = True if occupancy == '1' else False

            occupancy_status = {
                'type': 'occupancy_status',
                'status': room_occupied,
                'timestamp': datetime.now()  # Timestamp for when the response was received
            }

            return occupancy_status

        except Exception as e:
            logger.error(f"Error parsing room occupancy response: {response} - Error: {e}")
            raise

