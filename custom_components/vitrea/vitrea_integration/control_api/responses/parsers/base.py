# parsers/base.py

from abc import ABC, abstractmethod

class ResponseParser(ABC):
    """
    Abstract base class for all response parsers. Each specific parser will
    inherit from this class and implement the parse method.
    """

    @abstractmethod
    async def parse(self, response):
        """
        Parse the given response string into a structured format.

        :param response: The raw response string from the VBox.
        :return: A structured dictionary with the parsed data.
        """
        pass
