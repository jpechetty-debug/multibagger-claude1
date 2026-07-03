import datetime
import json
import logging
import os
import sys


class JSONFormatter(logging.Formatter):
    """Custom JSON Formatter for structured logging."""

    def format(self, record):
        log_record = {
            "timestamp": datetime.datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "module": record.module,
            "func": record.funcName,
            "message": record.getMessage(),
        }
        # Include extra context if provided
        if hasattr(record, "extra_context"):
            log_record.update(record.extra_context)

        # Include exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


class ConsoleFormatter(logging.Formatter):
    """Clean color-coded formatter for terminal output."""

    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    format_str = "%(asctime)s - %(levelname)s - %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: grey + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


def get_structured_logger(name="sovereign", log_file="logs/sovereign.json"):
    """Initialize and return a structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Ensure log directory exists when a directory component is provided.
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 1. JSON File Handler (Machine Readable)
    fh = logging.FileHandler(log_file)
    fh.setFormatter(JSONFormatter())
    logger.addHandler(fh)

    # 2. Console Handler (Human Readable)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ConsoleFormatter())
    logger.addHandler(ch)

    return logger


def format_log_message(*args, sep=" ", end="\n"):
    """Render print-style arguments as a single log message."""
    message = sep.join(str(arg) for arg in args)
    if end and end != "\n":
        message += end
    return message


class SovereignLogger:
    """Wrapper class to simplify extra context logging."""

    def __init__(self, name="sovereign", log_file="logs/sovereign.json"):
        self._logger = get_structured_logger(name, log_file=log_file)

    @property
    def logger(self):
        return self._logger

    def _log(self, level, msg, *args, **kwargs):
        if args:
            try:
                msg = msg % args
            except TypeError:
                msg = f"{msg} {args}"
        if kwargs:
            self._logger.log(level, msg, extra={"extra_context": kwargs})
        else:
            self._logger.log(level, msg)

    def info(self, msg, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)


def get_logger(name="sovereign", log_file="logs/sovereign.json"):
    """Return the project-standard structured logger wrapper."""
    return SovereignLogger(name, log_file=log_file)


# Global default instances
logger = SovereignLogger()
log = SovereignLogger("sovereign")
