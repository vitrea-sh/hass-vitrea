# parsers/ack_response_parser.py
from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class AckResponseParser(ResponseParser):
    def parse(self, response: str):
        """
        Parses an acknowledgment (ACK) response from the VBox.

        Expected format: S:PSW:OK <CR><LF>

        :param response: The raw response string from the VBox.
        :return: A structured dictionary confirming the acknowledgment.
        """
        result = {
            "type": "acknowledgment",
            "subtype": None,
            "timestamp": datetime.now(),
        }
        if response == "OK":
            result["subtype"] = "action_executed"
        else:
            response = response.strip()
            parts = response.split(":")
            if (
                len(parts) == 3
                and parts[0] == "S"
                and parts[1] == "PSW"
                and parts[2] == "OK"
            ):
                result["subtype"] = "keep_alive_acknowledgment"
            else:
                logger.error(format("Error parsing ACK response: %s", response))
        return result
