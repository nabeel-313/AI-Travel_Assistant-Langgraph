import sys


def error_message_detail(error: Exception):
    """Format detailed error message with file name and line number."""
    exc_type, exc_value, exc_tb = sys.exc_info()
    if exc_tb is not None:
        file_name = exc_tb.tb_frame.f_code.co_filename
        line_number = exc_tb.tb_lineno
    else:
        file_name = "<unknown>"
        line_number = "?"
    return f"Error occurred in script [{file_name}] line [{line_number}] - {error}"


class ExceptionError(Exception):
    def __init__(self, error: Exception):
        self.error_message = error_message_detail(error)
        super().__init__(self.error_message)

    def __str__(self):
        return self.error_message
