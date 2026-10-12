"""JSON-lines logging to stderr."""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """One JSON object per record: ts (UTC ISO), level, logger, msg, and exc if present."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record as a single JSON line."""
        out = {"ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out)


def setup_logging(level: str = "INFO") -> None:
    """Make the root logger emit JSON to stderr through a single handler; safe to repeat."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
