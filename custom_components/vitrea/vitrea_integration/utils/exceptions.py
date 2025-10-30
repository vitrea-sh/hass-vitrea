class VitreaException(Exception):
    def __init__(self, message):
        super().__init__(message)


class WrongCommandException(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Wrong Command: {self.message}"


class WrongInputExcpetion(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Wrong Input: {self.message}"


class WrongNodeNumberException(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Wrong Node Number: {self.message}"


class WrongKeyNumberException(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Wrong Key Number: {self.message}"


class NodeNotFoundException(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Node Not Found: {self.message}"


class WrongScenarioException(VitreaException):
    def __init__(self, message):
        super().__init__(message)

    def __str__(self):
        return f"Wrong Scenario: {self.message}"
