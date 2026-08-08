"""
monitoring/logger.py — Structured JSON logging for S.A.A.S.
============================================================
Replaces all print() / basicConfig() calls.
Outputs structured JSON logs — searchable, filterable, alertable.

Usage:
    from monitoring.logger import get_logger
    log = get_logger("WARD-AGENT")
    log.info("AQI updated", extra={"ward": "Ward-1", "aqi": 420})
"""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

LOG_DIR  = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "saas.log"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

_configured = False

class SAASlFormatter(logging.Formatter):
    """JSON-structured log formatter."""
    def format(self, record: logging.LogRecord) -> str:
        import json
        log_entry = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
            "module":  record.module,
            "line":    record.lineno,
        }
        # Include any extra fields passed via extra={}
        for key in vars(record):
            if key not in ("name","msg","args","levelname","levelno","pathname",
                           "filename","module","exc_info","exc_text","stack_info",
                           "lineno","funcName","created","msecs","relativeCreated",
                           "thread","threadName","processName","process","message"):
                log_entry[key] = getattr(record, key)
        if record.exc_info:
            log_entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)

class HumanFormatter(logging.Formatter):
    """Human-readable formatter for console."""
    COLOURS = {
        "DEBUG":    "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        col   = self.COLOURS.get(record.levelname, "")
        reset = self.RESET
        ts    = datetime.now(timezone.utc).strftime("%H:%M:%S")
        return f"{col}{ts}  {record.levelname:<8s}{reset}  [{record.name}]  {record.getMessage()}"


def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # Console — human readable
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(HumanFormatter())
    ch.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    root.addHandler(ch)

    # File — structured JSON
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(SAASlFormatter())
    fh.setLevel(logging.DEBUG)
    root.addHandler(fh)

    root.info("Logging initialised — JSON → %s | Console → stdout", LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
