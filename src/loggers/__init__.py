import logging
import os
import sys
import json
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, Optional

from from_root import from_root


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread_id": record.thread,
        }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # Add any custom fields from extra dict
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, default=str)


class TextFormatter(logging.Formatter):
    """Text formatter with consistent format."""

    def __init__(self):
        super().__init__(
            fmt="[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )


class RequestContextFilter(logging.Filter):
    """Add request context to log records."""

    _request_id: Optional[str] = None
    _user_id: Optional[str] = None
    _session_id: Optional[str] = None

    @classmethod
    def set_context(cls, request_id: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
        cls._request_id = request_id
        cls._user_id = user_id
        cls._session_id = session_id

    @classmethod
    def clear_context(cls):
        cls._request_id = None
        cls._user_id = None
        cls._session_id = None

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = self._request_id
        record.user_id = self._user_id
        record.session_id = self._session_id
        return True


class Logger:
    """Production-grade reusable application logger."""

    _loggers: Dict[str, logging.Logger] = {}
    _initialized: bool = False
    _log_format: str = "json"  # json or text
    _log_dir: str = "logs"
    _max_file_size: int = 100 * 1024 * 1024  # 100MB
    _backup_count: int = 5

    def __init__(
        self,
        name: str = __name__,
        log_format: str = "json",
        log_level: int = logging.INFO
    ):
        self.name = name
        self._log_format = log_format
        self._log_level = log_level
        self._setup_logger()

    @classmethod
    def configure(
        cls,
        log_format: str = "json",
        log_dir: str = "logs",
        max_file_size_mb: int = 100,
        backup_count: int = 5,
        log_level: int = logging.INFO
    ):
        """Configure logger class settings."""
        cls._log_format = log_format
        cls._log_dir = log_dir
        cls._max_file_size = max_file_size_mb * 1024 * 1024
        cls._backup_count = backup_count
        cls._initialized = True

        # Clear existing loggers to apply new settings
        cls._loggers.clear()

    def _setup_logger(self):
        """Setup logger with handlers and formatters."""
        if self.name in Logger._loggers:
            self.logger = Logger._loggers[self.name]
            return

        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self._log_level)
        self.logger.propagate = False

        # Remove existing handlers
        self.logger.handlers.clear()

        # Create log directory
        logs_path = os.path.join(from_root(), self._log_dir)
        os.makedirs(logs_path, exist_ok=True)

        # Determine formatter
        if self._log_format == "json":
            formatter = JSONFormatter()
        else:
            formatter = TextFormatter()

        # File handler with rotation
        log_file = os.path.join(logs_path, f"{datetime.now().strftime('%m_%d_%Y')}.log")
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=self._max_file_size,
            backupCount=self._backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(self._log_level)
        self.logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self._log_level)
        self.logger.addHandler(console_handler)

        # Add request context filter
        self.logger.addFilter(RequestContextFilter())

        Logger._loggers[self.name] = self.logger

    def get_logger(self) -> logging.Logger:
        """Return the logger instance."""
        return self.logger

    def set_level(self, level: int):
        """Set log level."""
        self.logger.setLevel(level)
        for handler in self.logger.handlers:
            handler.setLevel(level)

    @staticmethod
    def with_context(request_id: Optional[str] = None, user_id: Optional[str] = None, session_id: Optional[str] = None):
        """Context manager for request-scoped logging."""
        RequestContextFilter.set_context(request_id, user_id, session_id)
        try:
            yield
        finally:
            RequestContextFilter.clear_context()


# Convenience function for quick access
def get_logger(name: str = __name__) -> logging.Logger:
    """Get or create a logger instance."""
    if name not in Logger._loggers:
        Logger(name)
    return Logger._loggers[name]


# Module-level logger for imports
#logging = get_logger(__name__)
# Module-level logger for imports
module_logger = get_logger(__name__)
