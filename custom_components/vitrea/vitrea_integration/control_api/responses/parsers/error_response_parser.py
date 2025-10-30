# parsers/error_response_parser.py
from .base import ResponseParser
from ....utils.exceptions import (
    NodeNotFoundException,
    WrongCommandException,
    WrongInputExcpetion,
    WrongKeyNumberException,
    WrongNodeNumberException,
    WrongScenarioException,
    VitreaException,
)
import logging

logger = logging.getLogger(__name__)


class ErrorResponseParser(ResponseParser):
    def parse(self, response):
        _, error_code, message = response.split(":")
        if not error_code.isdigit():
            raise VitreaException(
                f"Error Received With Invalid error code {error_code}, Full Message: {response}"
            )
        match int(error_code):
            case 1:
                raise WrongCommandException(message.strip())
            case 2:
                raise WrongNodeNumberException(message.strip())
            case 3:
                raise WrongKeyNumberException(message.strip())
            case 4:
                raise WrongInputExcpetion(message.strip())
            case 5:
                raise WrongScenarioException(message.strip())
            case 6:
                raise NodeNotFoundException(message.strip())
            case _:
                raise VitreaException(message.strip())
