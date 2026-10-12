"""FastAPI app factory. No side effects at import.

Run: uvicorn --factory api.main:create_app
"""

import logging
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from api.db import connect, init_db
from api.settings import Settings
from core.live import live_regime
from core.regime import Regime

log = logging.getLogger("varta.api")
REGIME_TTL_SECONDS = 300


def create_app(
    settings: Settings | None = None,
    regime_provider: Callable[[], Regime] = live_regime,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    """Build the API: initialise the DB and register routes."""
    settings = settings or Settings.from_env()
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)

    app = FastAPI(title="Vārtā API")
    # ponytail: single-process in-memory cache; move to the DB if the api runs >1 worker
    cache: dict[str, tuple[float, Regime]] = {}

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness plus a trivial DB query."""
        with closing(connect(settings.db_path)) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "instance": settings.instance}

    @app.get("/api/regime")
    def regime() -> dict:
        """Current market regime, cached for REGIME_TTL_SECONDS."""
        hit = cache.get("regime")
        if hit and clock() - hit[0] < REGIME_TTL_SECONDS:
            return asdict(hit[1])
        try:
            result = regime_provider()
        except Exception as exc:  # network, short history, bad prices
            log.warning("regime unavailable: %s", exc)
            raise HTTPException(status_code=503, detail="regime unavailable") from exc
        cache["regime"] = (clock(), result)
        return asdict(result)

    return app
