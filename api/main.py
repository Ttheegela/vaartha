"""FastAPI app factory. No side effects at import.

Run: uvicorn --factory api.main:create_app
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager, closing
from dataclasses import asdict
from datetime import date
from typing import Literal

import polars as pl
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from api.advisor import build_advisor_router
from api.agent import llm_client
from api.agent_tools import build_toolbox
from api.crypto import TokenBox
from api.db import connect, init_db
from api.finance import build_finance_router
from api.logs import setup_logging
from api.news_read import build_news_router
from api.plaid_client import PlaidAPI, PlaidClient, PlaidError
from api.settings import DEMO_ADMIN_RATE, Settings, local_today
from api.sync import STATUS_NOT_FOUND, institution_linked, link_item, sync_all
from api.visitor import RateLimiter, client_ip
from core.live import live_regime
from core.prices import fetch_closes
from core.regime import Regime
from worker import main as worker_main

log = logging.getLogger("varta.api")
link_log = logging.getLogger("varta.plaid_link")
REGIME_TTL_SECONDS = 300
PLAID_PRODUCTS = ["transactions"]
PLAID_CONSENTED = ["investments"]  # consent at Link, billed on first holdings call
WORKER_JOIN_SECONDS = 5
HTTPS_REDIRECT_STATUS = 308  # permanent, keeps method and body
LINK_EVENT_RATE = 120  # Link telemetry posts per IP per hour on the demo (a session sends ~10)
LINK_FIELD_MAX = 128


class RegimeOut(BaseModel):
    """Regime as served to clients."""

    label: Literal["Normal", "Elevated", "Crisis"]
    prob: float
    brent_vol: float
    spy_dd: float
    gold_oil: float
    signals: dict[str, float]


class LinkTokenIn(BaseModel):
    """Optional item_id: create an update-mode (reconnect) token for that item."""

    item_id: str | None = None


class LinkTokenOut(BaseModel):
    """Plaid Link token for the client."""

    link_token: str


class ExchangeIn(BaseModel):
    """Public token returned by Plaid Link, plus the institution from onSuccess metadata."""

    public_token: str
    institution_id: str | None = None


class ExchangeOut(BaseModel):
    """Linked item id."""

    item_id: str


class LinkEventIn(BaseModel):
    """Plaid Link onEvent/onExit/onSuccess metadata. Unknown fields (tokens) are dropped."""

    event: str = Field(max_length=LINK_FIELD_MAX)
    link_session_id: str | None = Field(default=None, max_length=LINK_FIELD_MAX)
    institution_id: str | None = Field(default=None, max_length=LINK_FIELD_MAX)
    error_type: str | None = Field(default=None, max_length=LINK_FIELD_MAX)
    error_code: str | None = Field(default=None, max_length=LINK_FIELD_MAX)
    view_name: str | None = Field(default=None, max_length=LINK_FIELD_MAX)
    request_id: str | None = Field(default=None, max_length=LINK_FIELD_MAX)


class SyncOut(BaseModel):
    """Per-item sync status: "ok" or a Plaid error code."""

    items: dict[str, str]


def create_app(
    settings: Settings | None = None,
    regime_provider: Callable[[], Regime] = live_regime,
    clock: Callable[[], float] = time.monotonic,
    today: Callable[[], date] | None = None,
    plaid: PlaidAPI | None = None,
    llm=None,
    closes_provider: Callable[[list[str]], pl.DataFrame] = lambda t: fetch_closes(t, "1y"),
) -> FastAPI:
    """Build the API: initialise the DB and register routes."""
    setup_logging()
    settings = settings or Settings.from_env()
    today = today or (lambda: local_today(settings.tz))
    with closing(connect(settings.db_path)) as conn:
        init_db(conn)

    if plaid is None and settings.plaid_configured:
        plaid = PlaidClient(settings.plaid_env, settings.plaid_client_id, settings.plaid_secret)
    if plaid is not None and not settings.token_key:
        raise ValueError("TOKEN_ENCRYPTION_KEY is required when Plaid is configured")
    box = TokenBox(settings.token_key) if settings.token_key else None

    admin_limiter = RateLimiter(DEMO_ADMIN_RATE if settings.instance == "demo" else 0)
    link_event_limiter = RateLimiter(LINK_EVENT_RATE if settings.instance == "demo" else 0)

    def require_plaid(request: Request) -> PlaidAPI:
        if not admin_limiter.allow(client_ip(request, settings.trust_proxy)):
            raise HTTPException(status_code=429, detail=f"rate limit: {DEMO_ADMIN_RATE} per hour")
        if plaid is None or box is None:
            raise HTTPException(status_code=503, detail="plaid not configured")
        return plaid

    def worker_body(stop: threading.Event) -> None:
        worker_main.boot_reseed_if_empty(settings)
        worker_main.run_loop(settings, stop)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop, thread = threading.Event(), None
        if settings.run_worker:
            thread = threading.Thread(target=worker_body, args=(stop,), name="varta-worker",
                                      daemon=True)
            thread.start()
        yield
        stop.set()
        if thread:
            thread.join(WORKER_JOIN_SECONDS)

    app = FastAPI(title="Vārtā API", lifespan=lifespan)
    if settings.cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_credentials=True, allow_methods=["GET", "POST"],
                           allow_headers=["content-type"])
    if settings.trust_proxy:
        @app.middleware("http")
        async def force_https(request: Request, call_next):
            """Redirect plain-http requests (per X-Forwarded-Proto) to https."""
            if request.headers.get("x-forwarded-proto") == "http":
                return RedirectResponse(str(request.url.replace(scheme="https")),
                                        status_code=HTTPS_REDIRECT_STATUS)
            return await call_next(request)

    # ponytail: single-process in-memory cache; move to the DB if the api runs >1 worker
    cache: dict[str, tuple[float, Regime]] = {}

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness plus a trivial DB query."""
        with closing(connect(settings.db_path)) as conn:
            conn.execute("SELECT 1")
        return {"status": "ok", "instance": settings.instance}

    def current_regime() -> Regime:
        """Regime cached for REGIME_TTL_SECONDS; raises if the provider fails."""
        hit = cache.get("regime")
        if hit and clock() - hit[0] < REGIME_TTL_SECONDS:
            return hit[1]
        result = regime_provider()
        cache["regime"] = (clock(), result)
        return result

    @app.get("/api/regime", response_model=RegimeOut)
    def regime() -> dict:
        """Current market regime, cached for REGIME_TTL_SECONDS."""
        try:
            return asdict(current_regime())
        except Exception as exc:  # network, short history, bad prices
            log.warning("regime unavailable: %s", exc)
            raise HTTPException(status_code=503, detail="regime unavailable") from exc

    app.include_router(build_finance_router(settings.db_path, today))
    app.include_router(build_news_router(settings.db_path, today))
    if llm is None and settings.llm_configured:
        llm = llm_client(settings)
    toolbox = build_toolbox(settings.db_path, today, current_regime, closes_provider)
    app.include_router(build_advisor_router(
        settings.db_path, toolbox, llm, settings.llm_model, settings))

    @app.post("/api/plaid/link_token", response_model=LinkTokenOut)
    def plaid_link_token(request: Request, body: LinkTokenIn | None = None) -> LinkTokenOut:
        """Create a Link token; with item_id, an update-mode token to reconnect that item."""
        p = require_plaid(request)
        access_token = None
        if body and body.item_id:
            with closing(connect(settings.db_path)) as conn:
                row = conn.execute("SELECT access_token_enc, status FROM items WHERE item_id=?",
                                   (body.item_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="unknown item")
            if row["status"] == STATUS_NOT_FOUND:
                raise HTTPException(status_code=409, detail="item removed at Plaid; link again")
            access_token = box.open(row["access_token_enc"])
        try:
            return LinkTokenOut(link_token=p.link_token_create(
                settings.instance, PLAID_PRODUCTS, PLAID_CONSENTED,
                redirect_uri=settings.plaid_redirect_uri, access_token=access_token))
        except PlaidError as exc:
            raise HTTPException(status_code=502, detail=exc.code) from exc

    @app.post("/api/plaid/exchange", response_model=ExchangeOut)
    def plaid_exchange(body: ExchangeIn, request: Request) -> ExchangeOut:
        """Exchange Link's public token and run the first sync; refuse a duplicate bank."""
        p = require_plaid(request)
        with closing(connect(settings.db_path)) as conn:
            if body.institution_id and institution_linked(conn, body.institution_id):
                raise HTTPException(status_code=409, detail="institution already linked")
            try:
                return ExchangeOut(item_id=link_item(conn, p, box, body.public_token, today()))
            except PlaidError as exc:
                raise HTTPException(status_code=502, detail=exc.code) from exc

    @app.post("/api/plaid/link_event", status_code=204)
    def plaid_link_event(body: LinkEventIn, request: Request) -> Response:
        """Log one Link telemetry event as JSON (link_session_id is what Plaid support needs)."""
        if not link_event_limiter.allow(client_ip(request, settings.trust_proxy)):
            raise HTTPException(status_code=429, detail=f"rate limit: {LINK_EVENT_RATE} per hour")
        link_log.info(json.dumps(body.model_dump()))
        return Response(status_code=204)

    @app.post("/api/sync", response_model=SyncOut)
    def sync(request: Request) -> SyncOut:
        """Sync every linked item; per-item status, never a 500 for one bad item."""
        p = require_plaid(request)
        with closing(connect(settings.db_path)) as conn:
            return SyncOut(items=sync_all(conn, p, box, today()))

    return app
