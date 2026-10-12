"""FastAPI app factory. No side effects at import.

Run: uvicorn --factory api.main:create_app
"""

import logging
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.crypto import TokenBox
from api.db import connect, init_db
from api.finance import build_finance_router
from api.news_read import build_news_router
from api.plaid_client import PlaidAPI, PlaidClient, PlaidError
from api.settings import Settings
from api.sync import link_item, sync_all
from core.live import live_regime
from core.regime import Regime

log = logging.getLogger("varta.api")
REGIME_TTL_SECONDS = 300
PLAID_PRODUCTS = ["transactions"]
PLAID_IF_SUPPORTED = ["investments"]


class RegimeOut(BaseModel):
    """Regime as served to clients."""

    label: Literal["Normal", "Elevated", "Crisis"]
    prob: float
    brent_vol: float
    spy_dd: float
    gold_oil: float
    signals: dict[str, float]


class LinkTokenOut(BaseModel):
    """Plaid Link token for the client."""

    link_token: str


class ExchangeIn(BaseModel):
    """Public token returned by Plaid Link."""

    public_token: str


class ExchangeOut(BaseModel):
    """Linked item id."""

    item_id: str


class SyncOut(BaseModel):
    """Per-item sync status: "ok" or a Plaid error code."""

    items: dict[str, str]


def create_app(
    settings: Settings | None = None,
    regime_provider: Callable[[], Regime] = live_regime,
    clock: Callable[[], float] = time.monotonic,
    today: Callable[[], date] = date.today,
    plaid: PlaidAPI | None = None,
) -> FastAPI:
    """Build the API: initialise the DB and register routes."""
    settings = settings or Settings.from_env()
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)

    if plaid is None and settings.plaid_configured:
        plaid = PlaidClient(settings.plaid_env, settings.plaid_client_id, settings.plaid_secret)
    if plaid is not None and not settings.token_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required when Plaid is configured")
    box = TokenBox(settings.token_key) if settings.token_key else None

    def require_plaid() -> PlaidAPI:
        if plaid is None or box is None:
            raise HTTPException(status_code=503, detail="plaid not configured")
        return plaid

    app = FastAPI(title="Vārtā API")
    # ponytail: single-process in-memory cache; move to the DB if the api runs >1 worker
    cache: dict[str, tuple[float, Regime]] = {}

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness plus a trivial DB query."""
        with closing(connect(settings.db_path)) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "instance": settings.instance}

    @app.get("/api/regime", response_model=RegimeOut)
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

    app.include_router(build_finance_router(settings.db_path, today))
    app.include_router(build_news_router(settings.db_path, today))

    @app.post("/api/plaid/link_token", response_model=LinkTokenOut)
    def plaid_link_token() -> LinkTokenOut:
        """Create a Plaid Link token for this instance's single user."""
        p = require_plaid()
        try:
            return LinkTokenOut(link_token=p.link_token_create(
                settings.instance, PLAID_PRODUCTS, PLAID_IF_SUPPORTED))
        except PlaidError as exc:
            raise HTTPException(status_code=502, detail=exc.code) from exc

    @app.post("/api/plaid/exchange", response_model=ExchangeOut)
    def plaid_exchange(body: ExchangeIn) -> ExchangeOut:
        """Exchange Link's public token and run the first sync."""
        p = require_plaid()
        with closing(connect(settings.db_path)) as conn:
            try:
                return ExchangeOut(item_id=link_item(conn, p, box, body.public_token, today()))
            except PlaidError as exc:
                raise HTTPException(status_code=502, detail=exc.code) from exc

    @app.post("/api/sync", response_model=SyncOut)
    def sync() -> SyncOut:
        """Sync every linked item; per-item status, never a 500 for one bad item."""
        p = require_plaid()
        with closing(connect(settings.db_path)) as conn:
            return SyncOut(items=sync_all(conn, p, box, today()))

    return app
