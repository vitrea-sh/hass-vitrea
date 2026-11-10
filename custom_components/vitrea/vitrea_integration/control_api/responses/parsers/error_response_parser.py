# parsers/error_response_parser.py
from .base import ResponseParser
import logging

logger = logging.getLogger(__name__)


class ErrorResponseParser(ResponseParser):
    """Parse controller error frames: E:Nxxx:K:PPP (spec section 6)."""

    ERROR_CODES = {
        1: "Wrong Command",
        2: "Wrong Input",
        3: "Wrong Node Number",
        4: "Wrong Key Number",
        5: "Node not found",
        6: "Wrong Scenario",
    }

    def parse(self, response: str):
        parts = response.strip().split(":")
        node_id = None
        key = None
        if len(parts) >= 4 and parts[1][:1] == "N" and parts[1][1:].isdigit():
            node_id = int(parts[1][1:])
            key = parts[2]
        code_field = parts[-1].strip()
        error_code = int(code_field) if code_field.isdigit() else None
        description = self.ERROR_CODES.get(error_code, "Unknown Error")
        logger.warning(
            "Vitrea controller rejected a command (node=%s key=%s): %s (code=%s, raw=%s)",
            node_id,
            key,
            description,
            error_code,
            response,
        )
        return {
            "type": "error",
            "node_id": node_id,
            "key": key,
            "error_code": error_code,
            "description": description,
        }
