import logging
import logging.handlers
import os
import sys
from pathlib import Path



"""
logging_config.py — Structured logging setup for the trading bot.
Produces two outputs simultaneously:
  1. Console  — human-readable, coloured (if supported), INFO and above.
  2. Log file — machine-readable JSON-style lines, DEBUG and above,
                stored in ./logs/trading_bot.log with daily rotation.
Call `setup_logging()` once at application start (done inside cli.py).
Use `get_logger(__name__)` everywhere else.
"""

# TODO: Add a separate trade-history log (CSV or JSONL) for backtesting.
# TODO: Support structured JSON console output for production log-shippers
#       (e.g. Datadog, Loki) via an env flag LOG_FORMAT=json.
# TODO: Ship logs to a remote sink (CloudWatch, GCP Logging) for prod.



LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "trading_bot.log"
TRADE_LOG_FILE = LOG_DIR / "trade_history.log"   # TODO: populate in orders.py

DEFAULT_LEVEL_CONSOLE = logging.INFO
DEFAULT_LEVEL_FILE = logging.DEBUG

# Colour codes for the console formatter (ANSI)
LEVEL_COLOURS = {
    "DEBUG":    "\033[36m",    # cyan
    "INFO":     "\033[32m",    # green
    "WARNING":  "\033[33m",    # yellow
    "ERROR":    "\033[31m",    # red
    "CRITICAL": "\033[1;31m",  # bold red
}
RESET = "\033[0m"


class ColouredFormatter(logging.Formatter):
    """Adds ANSI colour codes to log level names for terminal output."""

    def format(self, record: logging.LogRecord) -> str:
        colour = LEVEL_COLOURS.get(record.levelname, "")
        record.levelname = f"{colour}{record.levelname:<8}{RESET}"
        return super().format(record)


class FileFormatter(logging.Formatter):
    """
    Produces a consistent single-line format suitable for log parsers.
    Example:
        2025-07-01 12:34:56,789 | INFO     | bot.orders | Placing order ...
    """

    def format(self, record: logging.LogRecord) -> str:
        return super().format(record)


_CONSOLE_FMT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_FILE_FMT    = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FMT    = "%Y-%m-%d %H:%M:%S"

_logging_ready = False


def setup_logging(
    console_level: int = DEFAULT_LEVEL_CONSOLE,
    file_level: int = DEFAULT_LEVEL_FILE,
    log_dir: Path = LOG_DIR,) -> None:
    
    
    """
    Configure root logger with console + rotating-file handlers.
    Safe to call multiple times (idempotent).
    """

    global _logging_ready
    if _logging_ready:
        return

    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # handlers filter independently

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    use_colour = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
    console_handler.setFormatter(
        ColouredFormatter(_CONSOLE_FMT, datefmt=_DATE_FMT)
        if use_colour
        else logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
    
    root.addHandler(console_handler)

    # ------------------------------------------------------------------ #
    # Rotating file handler (10 MB × 5 backups)
    # TODO: Switch to TimedRotatingFileHandler for daily rotation

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "trading_bot.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",)
    
    file_handler.setLevel(file_level)
    file_handler.setFormatter(FileFormatter(_FILE_FMT, datefmt=_DATE_FMT))
    root.addHandler(file_handler)

    # ------------------------------------------------------------------ #
    # Trade history log — append-only JSONL
    # TODO: Write structured trade records here from orders.py

    trade_handler = logging.FileHandler(
        filename=log_dir / "trade_history.log",
        mode="a",
        encoding="utf-8",)
    

    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(FileFormatter(_FILE_FMT, datefmt=_DATE_FMT))
    # Only the dedicated trade logger writes here
    trade_logger = logging.getLogger("trade_history")
    trade_logger.addHandler(trade_handler)
    trade_logger.propagate = False  # don't double-log to root

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    _logging_ready = True
    logging.getLogger(__name__).info(
        "Logging initialised. Console=%s | File=%s | LogDir=%s",
        logging.getLevelName(console_level),
        logging.getLevelName(file_level),
        log_dir.resolve(),)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.
    If setup_logging() hasn't been called yet (e.g. in tests),
    a basic configuration is applied automatically.
    """
    
    if not _logging_ready:
        logging.basicConfig(level=logging.DEBUG)
    return logging.getLogger(name)
