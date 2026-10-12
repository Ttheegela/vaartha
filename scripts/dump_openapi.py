"""Write the API's OpenAPI schema to web/openapi.json (input for openapi-typescript).

Run: uv run python -m scripts.dump_openapi
"""

import json
import tempfile
from pathlib import Path

from api.main import create_app
from api.settings import Settings

OUT = Path(__file__).resolve().parents[1] / "web" / "openapi.json"


def _no_regime():
    raise RuntimeError("schema dump never calls the provider")


def build_openapi() -> dict:
    """Build the schema from a throwaway app; no network, temp DB."""
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(db_path=Path(tmp) / "schema.db", instance="demo"),
                         regime_provider=_no_regime)
        return app.openapi()


if __name__ == "__main__":
    OUT.write_text(json.dumps(build_openapi(), indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")
