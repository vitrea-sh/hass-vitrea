from ...utils.exceptions import VitreaException
from .parsers import (
    ErrorResponseParser,
    StatusResponseParser,
    ScenarioStatusResponseParser,
    ACStatusResponseParser,
    ControllerClockResponseParser,
    OutputStatusResponseParser,
    InputStatusResponseParser,
    RoomOccupancyResponseParser,
    AckResponseParser,
    VersionResponseParser,
)
import logging

_LOGGER = logging.getLogger(__name__)


def get_parser(response_prefix):
    """
    Returns an instance of the appropriate parser based on the response prefix.

    :param response_prefix: The prefix of the response string indicating its type.
    :return: An instance of the corresponding parser.
    """
    parsers = {
        "E": ErrorResponseParser,
        "S:N": StatusResponseParser,
        "S:R": ScenarioStatusResponseParser,
        "S:A": ACStatusResponseParser,
        "T": ControllerClockResponseParser,
        "S:O": OutputStatusResponseParser,
        "S:I": InputStatusResponseParser,
        "S:C": RoomOccupancyResponseParser,
        "S:PSW": AckResponseParser,
        "V": VersionResponseParser,
        "OK": "",
        "ERROR": ErrorResponseParser,
    }

    # Select the parser class based on the response prefix
    parser_class = parsers.get(response_prefix)
    if parser_class:
        return parser_class()
    else:
        # If no exact match, check for startswith matches
        for prefix, parser_cls in parsers.items():
            if response_prefix.startswith(prefix):
                return parser_cls()
        raise ValueError(f"No parser available for response prefix: {response_prefix}")


def parse_response(response):
    """Parse an incoming message from the VBox and return a structured dictionary."""
    # Decode byte string to utf-8 if it's not already a string
    if isinstance(response, bytes):
        response = response.decode('utf-8', errors='replace').strip()
    # Extract the prefix for parser selection
    if len(response.split("\r\n")) > 1:
        response_parts = response.split("\r\n")
        multi_response = []
        for split_response in response_parts:
            multi_response.append(parse_response(split_response))
        return multi_response
    response_parts = response.split(":", 2)  # Split only on the first two colons
    if len(response_parts) < 2:
        if response == "OK":
            return {"type": "acknowledgment", "message": "Action Executed"}
        raise ValueError(f"Invalid response format: {response}")

    response_prefix = ":".join(response_parts[:2])

    try:
        parser = get_parser(response_prefix)
        parsed_response = parser.parse(response)  # Call parse on the instance
        return parsed_response
    except VitreaException as e:
        _LOGGER.error(f"Error from Vitrea Controller: {e}")
        return {}
    except ValueError as e:
        _LOGGER.error(f"Failed to parse response: {response}, with error: {e}")
        return {
            "type": "error",
            "subtype": "parsing_error",
        }
