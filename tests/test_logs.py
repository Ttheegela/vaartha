"""JSON log formatter."""

import json
import logging

from api.logs import JsonFormatter, setup_logging


def _rec(**kw):
    return logging.LogRecord("varta.x", logging.INFO, __file__, 1, "hello %s", ("w",),
                              kw.get("exc_info"))


def test_format_keys():
    d = json.loads(JsonFormatter().format(_rec()))
    assert d["msg"] == "hello w" and d["level"] == "INFO" and d["logger"] == "varta.x"
    assert d["ts"].endswith("+00:00") and "exc" not in d


def test_format_exc():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        d = json.loads(JsonFormatter().format(_rec(exc_info=sys.exc_info())))
    assert "ValueError" in d["exc"]


def test_setup_idempotent():
    setup_logging()
    setup_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
