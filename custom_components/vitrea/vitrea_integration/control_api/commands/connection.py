from .base import Command


class AuthenticateCommand(Command):
    TEMPLATE = "P:VITREA\r\n"

    def serialize(self):
        return self.TEMPLATE.encode()

    def validate(self):
        pass


class GetControllerVersionCommand(Command):
    TEMPLATE = "G:V:S\r\n"

    def serialize(self):
        return self.TEMPLATE.encode()

    def validate(self):
        pass
