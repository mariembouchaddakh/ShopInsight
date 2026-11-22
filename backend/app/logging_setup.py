"""Journalisation structurée avec masquage des secrets (clés OpenRouter, en-têtes Authorization)."""
from __future__ import annotations

import json
import logging
import re

_SECRET = re.compile(r"(sk-or-[A-Za-z0-9_\-]{4})[A-Za-z0-9_\-]+|(Bearer\s+)[A-Za-z0-9_\-\.]+", re.I)


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: (m.group(1) + "…") if m.group(1) else (m.group(2) + "…"), text)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(str(record.msg))
        if record.args:
            record.args = tuple(redact(str(a)) for a in record.args) if isinstance(record.args, tuple) else record.args
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"level": record.levelname, "logger": record.name, "message": redact(record.getMessage())}
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["error"] = redact(self.formatException(record.exc_info))
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("shopinsight")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler.addFilter(RedactingFilter())
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger
