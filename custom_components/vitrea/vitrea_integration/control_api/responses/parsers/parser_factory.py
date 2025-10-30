# parsers/parser_factory.py
from .error_response_parser import ErrorResponseParser
from .status_response_parser import StatusResponseParser
from .scenario_status_response_parser import ScenarioStatusResponseParser
from .ac_status_response_parser import ACStatusResponseParser
from .controller_clock_response_parser import ControllerClockResponseParser
from .output_status_response_parser import OutputStatusResponseParser
from .input_status_response_parser import InputStatusResponseParser
from .room_occupancy_response_parser import RoomOccupancyResponseParser
from .ack_response_parser import AckResponseParser
from .version_response_parser import VersionResponseParser
# ... import other specific parsers as needed


class ParserFactory:
    @staticmethod
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
            "ERROR": "",
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
            raise ValueError(
                f"No parser available for response prefix: {response_prefix}"
            )


# Usage:
# parser = ParserFactory.get_parser(response_prefix)
# parsed_data = parser.parse(response)
