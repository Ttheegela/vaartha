"""The committed web/openapi.json must match the live API schema."""

import json
from pathlib import Path

from scripts.dump_openapi import build_openapi

SNAPSHOT = Path(__file__).resolve().parents[1] / "web" / "openapi.json"


def test_regime_schema_is_typed():
    schema = build_openapi()
    regime = schema["components"]["schemas"]["RegimeOut"]
    assert regime["properties"]["label"]["enum"] == ["Normal", "Elevated", "Crisis"]


def test_snapshot_is_current():
    assert json.loads(SNAPSHOT.read_text()) == build_openapi(), (
        "API changed: run `uv run python scripts/dump_openapi.py` and `cd web && pnpm gen:api`"
    )
