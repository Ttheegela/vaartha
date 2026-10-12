"""Advisor HTTP API: SSE chat, conversations, alerts and the latest briefing."""

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.agent import build_messages, run_agent
from api.agent_tools import Toolbox
from api.briefing import parse_briefing
from api.db import connect

log = logging.getLogger("varta.advisor")
HISTORY_TURNS = 10
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


def build_advisor_router(db_path: Path, toolbox: Toolbox, llm, model: str) -> APIRouter:
    """Routes for chat, conversations, alerts and briefing over one database."""
    router = APIRouter(prefix="/api")

    def log_message(conn, conv: str, role: str, content: str | None, **cols) -> None:
        conn.execute(
            "INSERT INTO agent_messages (conversation_id, role, content, tool_calls, model, "
            "latency_ms, tokens_in, tokens_out) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conv, role, content, cols.get("tool_calls"), cols.get("model"),
             cols.get("latency_ms"), cols.get("tokens_in"), cols.get("tokens_out")))
        conn.commit()

    def stream(conv: str, message: str) -> Iterator[str]:
        yield _sse("meta", {"conversation_id": conv})
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT role, content FROM agent_messages WHERE conversation_id = ? "
                "AND role IN ('user', 'assistant') AND content IS NOT NULL "
                "ORDER BY id DESC LIMIT ?", (conv, HISTORY_TURNS)).fetchall()
            history = [dict(r) for r in reversed(rows)]
            log_message(conn, conv, "user", message)
            try:
                for ev in run_agent(llm, model, build_messages(toolbox, history, message),
                                    toolbox):
                    if ev["type"] == "answer":
                        answer = ev["text"]
                    elif ev["type"] == "done":
                        log_message(
                            conn, conv, "assistant", answer, model=ev["model"],
                            tool_calls=json.dumps({"calls": ev["tool_calls"],
                                                   "sources": ev["sources"]}),
                            latency_ms=ev["latency_ms"], tokens_in=ev["tokens_in"],
                            tokens_out=ev["tokens_out"])
                    yield _sse(ev["type"], {k: v for k, v in ev.items() if k != "type"})
            except Exception as exc:
                log.warning("advisor failed: %s", type(exc).__name__)
                log_message(conn, conv, "assistant", None,
                            tool_calls=json.dumps({"error": type(exc).__name__}))
                yield _sse("error", {"message": "advisor unavailable"})

    @router.post("/chat")
    def chat(body: ChatIn) -> StreamingResponse:
        """Stream the advisor's answer as server-sent events."""
        if llm is None:
            raise HTTPException(status_code=503, detail="advisor not configured")
        conv = body.conversation_id or uuid.uuid4().hex
        return StreamingResponse(stream(conv, body.message), media_type="text/event-stream",
                                 headers=SSE_HEADERS)

    @router.get("/conversations", response_model=list[ConversationOut])
    def conversations() -> list[dict]:
        """Newest conversations first; the title is the first user message."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT conversation_id AS id, MAX(created_at) AS updated_at, MAX(id) AS last, "
                "(SELECT content FROM agent_messages f WHERE f.conversation_id = m.conversation_id "
                "AND f.role = 'user' ORDER BY f.id LIMIT 1) AS title "
                "FROM agent_messages m GROUP BY conversation_id ORDER BY last DESC LIMIT ?",
                (MAX_CONVERSATIONS,)).fetchall()
        return [{"id": r["id"], "title": (r["title"] or "")[:TITLE_CHARS],
                 "updated_at": r["updated_at"]} for r in rows]

    @router.get("/conversations/{conversation_id}", response_model=list[MessageOut])
    def conversation(conversation_id: str) -> list[dict]:
        """User and assistant messages of one conversation, oldest first."""
        with closing(connect(db_path)) as conn:
            rows = conn.execute(
                "SELECT role, content, created_at, tool_calls FROM agent_messages "
                "WHERE conversation_id = ? ORDER BY id", (conversation_id,)).fetchall()
        if not rows:
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
        """Dismiss one alert."""
        with closing(connect(db_path)) as conn:
            cur = conn.execute("UPDATE alerts SET dismissed = 1 WHERE id = ?", (alert_id,))
            conn.commit()
        if not cur.rowcount:
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
