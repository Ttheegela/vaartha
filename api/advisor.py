"""Advisor HTTP API: SSE chat, conversations, alerts and the latest briefing."""

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.agent import build_messages, run_agent
from api.agent_tools import Toolbox
from api.briefing import parse_briefing
from api.db import connect
from api.settings import Settings
from api.visitor import (
    COOKIE_MAX_AGE,
    VISITOR_COOKIE,
    RateLimiter,
    client_ip,
    new_visitor_id,
    visitor_id,
)

log = logging.getLogger("varta.advisor")
HISTORY_MESSAGES = 10
MAX_MESSAGE_CHARS = 2000
MAX_CONVERSATION_ID_CHARS = 64
MAX_CONVERSATIONS = 50
TITLE_CHARS = 60
SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"}


class ChatIn(BaseModel):
    """A user message, optionally continuing a conversation."""

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    conversation_id: str | None = Field(
        default=None, max_length=MAX_CONVERSATION_ID_CHARS, pattern=r"^[A-Za-z0-9-]+$")


class SourceOut(BaseModel):
    """A news story cited in an answer."""

    id: int | None = None
    title: str | None = None
    source: str | None = None
    published_at: str | None = None


class ConversationOut(BaseModel):
    """Conversation list row."""

    id: str
    title: str
    updated_at: str


class MessageOut(BaseModel):
    """One user or assistant message."""

    role: str
    content: str
    created_at: str
    sources: list[SourceOut]
    tool_names: list[str]


class AlertOut(BaseModel):
    """An undismissed alert."""

    id: int
    created_at: str
    kind: str
    text: str
    action_label: str | None
    action_href: str | None


class BriefingOut(BaseModel):
    """The latest daily briefing."""

    date: str
    headline: str
    bullets: list[str]
    sources: list[SourceOut]
    model: str | None
    generated_at: str | None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def build_advisor_router(db_path: Path, toolbox: Toolbox, llm, model: str,
                         settings: Settings) -> APIRouter:
    """Routes for chat, conversations, alerts and briefing over one database."""
    router = APIRouter(prefix="/api")
    limiter = RateLimiter(settings.chat_rate_per_hour)
    demo = settings.instance == "demo"

    def log_message(conv: str, vid: str, role: str, content: str | None, **cols) -> None:
        # one short-lived connection per write: the stream hops threads between yields
        with closing(connect(db_path)) as conn:
            conn.execute(
                "INSERT INTO agent_messages (conversation_id, role, content, tool_calls, model, "
                "latency_ms, tokens_in, tokens_out, visitor_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (conv, role, content, cols.get("tool_calls"), cols.get("model"),
                 cols.get("latency_ms"), cols.get("tokens_in"), cols.get("tokens_out"), vid))
            conn.commit()

    def load_history(conv: str) -> list[dict]:
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT role, content FROM agent_messages WHERE conversation_id = ? "
                "AND role IN ('user', 'assistant') AND content IS NOT NULL "
                "ORDER BY id DESC LIMIT ?", (conv, HISTORY_MESSAGES)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def stream(conv: str, vid: str, message: str) -> Iterator[str]:
        yield _sse("meta", {"conversation_id": conv})
        try:
            log_message(conv, vid, "user", message)
            history = load_history(conv)[:-1]  # drop the message just logged
            for ev in run_agent(llm, model, build_messages(toolbox, history, message), toolbox):
                if ev["type"] == "answer":
                    answer = ev["text"]
                elif ev["type"] == "done":
                    log_message(
                        conv, vid, "assistant", answer, model=ev["model"],
                        tool_calls=json.dumps({"calls": ev["tool_calls"],
                                               "sources": ev["sources"]}),
                        latency_ms=ev["latency_ms"], tokens_in=ev["tokens_in"],
                        tokens_out=ev["tokens_out"])
                yield _sse(ev["type"], {k: v for k, v in ev.items() if k != "type"})
        except Exception as exc:
            log.warning("advisor failed: %s", type(exc).__name__)
            try:
                log_message(conv, vid, "assistant", None,
                            tool_calls=json.dumps({"error": type(exc).__name__}))
            except Exception:  # the DB itself may be what failed
                log.warning("could not log advisor error")
            yield _sse("error", {"message": "advisor unavailable"})

    @router.post("/chat")
    def chat(body: ChatIn, request: Request) -> StreamingResponse:
        """Stream the advisor's answer as server-sent events."""
        if llm is None:
            raise HTTPException(status_code=503, detail="advisor not configured")
        if not limiter.allow(client_ip(request, settings.trust_proxy)):
            raise HTTPException(
                status_code=429,
                detail=f"rate limit: {settings.chat_rate_per_hour} messages per hour")
        vid = visitor_id(request)
        minted = vid is None
        vid = vid or new_visitor_id()
        conv = body.conversation_id
        if conv:
            with closing(connect(db_path)) as conn:
                owner = conn.execute("SELECT visitor_id FROM agent_messages "
                                     "WHERE conversation_id = ? LIMIT 1", (conv,)).fetchone()
            if owner is not None and owner["visitor_id"] != vid and demo:
                conv = None  # someone else's (or pre-migration) conversation: start fresh
        resp = StreamingResponse(stream(conv or uuid.uuid4().hex, vid, body.message),
                                 media_type="text/event-stream", headers=SSE_HEADERS)
        if minted:
            resp.set_cookie(VISITOR_COOKIE, vid, max_age=COOKIE_MAX_AGE, path="/", httponly=True,
                            samesite="lax", secure=settings.trust_proxy,
                            domain=settings.cookie_domain)
        return resp

    @router.get("/conversations", response_model=list[ConversationOut])
    def conversations(request: Request) -> list[dict]:
        """This visitor's conversations, newest first; the title is the first user message."""
        vid = visitor_id(request)
        if vid is None and demo:
            return []
        where, args = ("1", ()) if not demo else ("visitor_id = ?", (vid,))
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                # created_at is SQLite datetime('now'): UTC, no zone marker; emit ISO-8601 Z
                "SELECT conversation_id AS id, strftime('%Y-%m-%dT%H:%M:%SZ', MAX(created_at)) "
                "AS updated_at, MAX(id) AS last, "
                "(SELECT content FROM agent_messages f WHERE f.conversation_id = m.conversation_id "
                "AND f.role = 'user' ORDER BY f.id LIMIT 1) AS title "
                f"FROM agent_messages m WHERE {where} GROUP BY conversation_id "
                "ORDER BY last DESC LIMIT ?", (*args, MAX_CONVERSATIONS)).fetchall()
        return [{"id": r["id"], "title": (r["title"] or "")[:TITLE_CHARS],
                 "updated_at": r["updated_at"]} for r in rows]

    @router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
    def conversation(conversation_id: str, request: Request) -> list[dict]:
        """User and assistant messages of one conversation, oldest first."""
        vid = visitor_id(request)
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT role, content, strftime('%Y-%m-%dT%H:%M:%SZ', created_at) AS created_at, "
                "tool_calls FROM agent_messages "
                "WHERE conversation_id = ? AND (visitor_id = ? OR ?) ORDER BY id",
                (conversation_id, vid, not demo)).fetchall()
        if (vid is None and demo) or not rows:
            raise HTTPException(status_code=404, detail="conversation not found")
        out = []
        for r in rows:
            if r["content"] is None:
                continue
            meta = json.loads(r["tool_calls"] or "{}")
            out.append({"role": r["role"], "content": r["content"], "created_at": r["created_at"],
                        "sources": meta.get("sources", []),
                        "tool_names": [c["name"] for c in meta.get("calls", [])]})
        return out

    @router.get("/alerts", response_model=list[AlertOut])
    def alerts() -> list[dict]:
        """Undismissed alerts, newest first."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT id, created_at, kind, text, action_label, action_href FROM alerts "
                "WHERE dismissed = 0 ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    @router.post("/alerts/{alert_id}/dismiss", status_code=204)
    def dismiss(alert_id: int) -> Response:
        """Dismiss one alert (a no-op on the shared demo)."""
        with closing(connect(db_path)) as conn:
            if demo:
                cur = conn.execute("SELECT 1 FROM alerts WHERE id = ?", (alert_id,))
                found = cur.fetchone() is not None
            else:
                cur = conn.execute("UPDATE alerts SET dismissed = 1 WHERE id = ?", (alert_id,))
                conn.commit()
                found = bool(cur.rowcount)
        if not found:
            raise HTTPException(status_code=404, detail="alert not found")
        return Response(status_code=204)

    @router.get("/briefing", response_model=BriefingOut | None)
    def briefing() -> dict | None:
        """The latest stored briefing, or null."""
        with closing(connect(db_path)) as conn:
            r = conn.execute("SELECT * FROM briefings ORDER BY date DESC LIMIT 1").fetchone()
        if r is None:
            return None
        stored = json.loads(r["items_json"])
        headline, bullets = parse_briefing(stored["text"])
        return {"date": r["date"], "headline": headline, "bullets": bullets,
                "sources": stored["sources"], "model": r["model"],
                "generated_at": r["generated_at"]}

    return router
