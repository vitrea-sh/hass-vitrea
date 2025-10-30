"""
Response parser for the get version command.
Example Response: b"V:866\r\n"
"""

from .base import ResponseParser
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class VersionResponseParser(ResponseParser):
    def parse(self, response):
        """
        Parses a version response from the VBox.

        Expected format: V:xxx <CR><LF>
        Where:
        - xxx is the version number.
        - <CR><LF> is the Carriage Return and Line Feed.

        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the version number.
        """
        try:
            response = response.strip()
            parts = response.split(":")
            if len(parts) < 2:
                raise ValueError("Incomplete version response")

            version = parts[1]
            major_version = version[0]
            minor_version = version[1:]

            return {
                "type": "version",
                "major_version": int(major_version),
                "minor_version": int(minor_version),
                "timestamp": datetime.now(),
            }
        except Exception as e:
            logger.error(f"Error parsing version response: {e}", exc_info=True)
            return None
