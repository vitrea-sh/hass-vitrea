# commands/base.py

class Command:
    async def serialize(self):
        """
        Serialize the command into the format that the VBox expects.
        This method must be implemented by all subclasses.

        :return: The serialized command string.
        """
        raise NotImplementedError("Subclasses must implement this method.")

    async def validate(self):
        """
        Validate the command parameters.
        This can be overridden by subclasses if specific validation logic is needed.

        :return: None
        :raises: ValueError if validation fails.
        """
        pass    