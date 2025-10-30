from typing import Callable
from .floors import FloorNumbersParser, FloorParamsParser
from .rooms import RoomNumbersParser, RoomParamsParser
from .keys import KeypadNumbersParser, KeyParamsParser
from .acs import ACNumbersParser, ACParamsParser
from .scenarios import ScenarioNumbersParser, ScenarioParamsParser
from .base import BaseParameterResponseParser

class DBResponseParserFactory:
    """
    Factory class for creating response parsers.
    """

    PARSERS = [FloorNumbersParser, FloorParamsParser, RoomNumbersParser, RoomParamsParser, KeypadNumbersParser, KeyParamsParser, ACNumbersParser, ACParamsParser, ScenarioNumbersParser, ScenarioParamsParser]

    @classmethod
    def create_parser(cls, raw_data:bytes, send_callback:Callable) -> BaseParameterResponseParser:
        """
        Creates a parser based on the command number.
        """
        command_number = int(raw_data.hex()[8:10], base=16)
        for parser in cls.PARSERS:
            if parser.COMMAND_NUMBER.value == command_number:
                return parser(raw_data, send_callback)
        return None