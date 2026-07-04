import logging
import os
from datetime import datetime

from from_root import from_root


class Logger:
    """Reusable application logger."""

    LOG_DIR = "logs"
    LOG_FILE = f"{datetime.now().strftime('%m_%d_%Y')}.log"

    def __init__(self, name: str = __name__):
        # Create log directory if it doesn’t exist
        logs_path = os.path.join(from_root(), self.LOG_DIR, self.LOG_FILE)
        os.makedirs(self.LOG_DIR, exist_ok=True)

        # Configure logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # Prevent duplicate handlers if re-imported
        if not self.logger.handlers:
            # File handler
            file_handler = logging.FileHandler(logs_path, encoding="utf-8")
            file_handler.setFormatter(self._get_formatter())
            self.logger.addHandler(file_handler)

            # Console handler (optional)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(self._get_formatter())
            self.logger.addHandler(console_handler)
        self.logger.propagate = False

    @staticmethod
    def _get_formatter():
        """Return a logging formatter with consistent format."""
        return logging.Formatter("[ %(asctime)s ] %(name)s - %(levelname)s - %(message)s")

    def get_logger(self):
        """Return the logger instance."""
        return self.logger
