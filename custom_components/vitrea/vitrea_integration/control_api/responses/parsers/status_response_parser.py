# parsers/status_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# TODO - DND, Ring etc...


class StatusResponseParser(ResponseParser):
    TYPE_MAPPINGS = {
        "O": "toggle_on",
        "F": "toggle_off",
        "D": "dimmer_intensity",
        "B": "blind_location",
        "S": "satellite_key_short",
        "L": "satellite_key_long",
        "R": "satellite_key_release",
        "o": "toggle_on",
        "f": "toggle_off",
        "M": "fan",
        "d": "hotel_dnd",
        "r": "hotel_ring",
        # Add more mappings if needed
    }

    STATUS_MAPPINGS = {
        "O": True,
        "F": False,
        "o": True,
        "f": False,
    }

    def parse(self, response):
        """
        Parses a status response from the VBox.

        Expected format: S:Nxxx:K:S:PP...P <CR><LF>
        Where:
        - Nxxx is the node number.
        - K is the key number (1-8 for nodes).
        - S is the status of the switch.
        - PP...P is the parameter of the command.
        - <CR><LF> is the Carriage Return and Line Feed.

        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the node status.
        """
        try:
            response = response.strip()
            parts = response.split(":")
            if len(parts) < 4:
                raise ValueError("Incomplete status response")

            node_id = int(parts[1][1:])
            key = int(parts[2])
            status_code = parts[3]
            params = parts[4] if len(parts) > 4 else None

            node_status = {
                "type": "node_status",
                "node_id": node_id,
                "key": key,
                "status": self.STATUS_MAPPINGS.get(status_code, None),
                "sub_type": self.TYPE_MAPPINGS.get(status_code, "unknown"),
                "parameters": params,
                "timestamp": datetime.now(),
            }

            return node_status

        except Exception as e:
            logger.error(f"Error parsing status response: {response} - Error: {e}")
            raise
