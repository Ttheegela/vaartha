"""Chat SSE, conversations, alerts and briefing endpoints with a fake LLM."""

import json
from datetime import date
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from api.agent_tools import build_toolbox
from api.briefing import make_briefing
from api.db import connect, init_db
from api.main import create_app
from api.settings import Settings
from core.regime import compute_regime

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _text(content):
    return NS(choices=[NS(message=NS(content=content, tool_calls=None))],
              usage=NS(prompt_tokens=10, completion_tokens=5))


def _tool(name):
    tc = NS(id="c1", function=NS(name=name, arguments="{}"))
    return NS(choices=[NS(message=NS(content=None, tool_calls=[tc]))],
              usage=NS(prompt_tokens=10, completion_tokens=5))


class FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw["messages"], default=str)))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _client(tmp_path, llm):
    settings = Settings(db_path=tmp_path / "v.db", instance="demo")
    app = create_app(settings, regime_provider=lambda: NORMAL, today=lambda: TODAY, llm=llm)
    return TestClient(app), settings


def _events(text):
    out = []
    for frame in text.strip().split("\n\n"):
        name, data = frame.split("\n")
        out.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


def test_chat_stream_and_logging(tmp_path):
    llm = FakeLLM(_tool("get_market_regime"), _text("All normal."), _text("Still normal."))
    c, settings = _client(tmp_path, llm)
    r = c.post("/api/chat", json={"message": "regime?"})
    assert "no-transform" in r.headers["cache-control"]
    assert r.headers["x-accel-buffering"] == "no"
    ev = _events(r.text)
    assert [e[0] for e in ev] == ["meta", "tool", "answer", "done"]
    conv = ev[0][1]["conversation_id"]
    assert ev[2][1]["text"] == "All normal."
    conn = connect(settings.db_path)
    assert [x["role"] for x in conn.execute("SELECT role FROM agent_messages")] == [
        "user", "assistant"]
    c.post("/api/chat", json={"message": "again", "conversation_id": conv})
    prior = [m["content"] for m in llm.calls[-1] if m["role"] in ("user", "assistant")]
    assert prior == ["regime?", "All normal.", "again"]


def test_503_without_llm(tmp_path):
    c, _ = _client(tmp_path, None)
    r = c.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503 and r.json() == {"detail": "advisor not configured"}


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "x" * 2001},
                                  {"message": "hi", "conversation_id": "bad id!"}])
def test_422(tmp_path, body):
    c, _ = _client(tmp_path, FakeLLM())
    assert c.post("/api/chat", json=body).status_code == 422


def test_llm_error_event(tmp_path):
    c, settings = _client(tmp_path, FakeLLM(RuntimeError("secret detail")))
    r = c.post("/api/chat", json={"message": "hi", "conversation_id": "c-1"})
    assert [e[0] for e in _events(r.text)] == ["meta", "error"]
    assert "secret" not in r.text
    rows = connect(settings.db_path).execute(
        "SELECT role, content, tool_calls FROM agent_messages ORDER BY id").fetchall()
    assert [(x["role"], x["content"]) for x in rows] == [("user", "hi"), ("assistant", None)]
    assert json.loads(rows[1]["tool_calls"]) == {"error": "RuntimeError"}
    assert c.get("/api/conversations/c-1").json()[0]["content"] == "hi"


def test_conversations(tmp_path):
    llm = FakeLLM(_text("one"), _text("two"))
    c, _ = _client(tmp_path, llm)
    c.post("/api/chat", json={"message": "a" * 100, "conversation_id": "c-1"})
    c.post("/api/chat", json={"message": "second", "conversation_id": "c-2"})
    lst = c.get("/api/conversations").json()
    assert [x["id"] for x in lst] == ["c-2", "c-1"]
    assert lst[1]["title"] == "a" * 60
    msgs = c.get("/api/conversations/c-1").json()
    assert [(m["role"], m["content"][:3]) for m in msgs] == [("user", "aaa"), ("assistant", "one")]
    assert c.get("/api/conversations/nope").status_code == 404


def test_sources_round_trip(tmp_path):
    c, settings = _client(tmp_path, FakeLLM(_text("x")))
    c.post("/api/chat", json={"message": "q", "conversation_id": "c-1"})
    conn = connect(settings.db_path)
    src = {"id": 1, "title": "T", "source": "S", "published_at": "2026-10-12"}
    conn.execute("UPDATE agent_messages SET tool_calls = ? WHERE role = 'assistant'",
                 (json.dumps({"calls": [{"name": "get_news", "args": {}}], "sources": [src]}),))
    conn.commit()
    last = c.get("/api/conversations/c-1").json()[1]
    assert last["sources"] == [src] and last["tool_names"] == ["get_news"]


def test_alerts_dismiss(tmp_path):
    c, settings = _client(tmp_path, None)
    conn = connect(settings.db_path)
    conn.execute("INSERT INTO alerts (created_at, kind, text) VALUES ('2026-10-12', 'k', 't')")
    conn.commit()
    got = c.get("/api/alerts").json()
    assert got[0]["text"] == "t"
    assert c.post(f"/api/alerts/{got[0]['id']}/dismiss").status_code == 204
    assert c.get("/api/alerts").json() == []
    assert c.post("/api/alerts/999/dismiss").status_code == 404


def test_briefing(tmp_path):
    c, settings = _client(tmp_path, None)
    assert c.get("/api/briefing").json() is None
    conn = connect(settings.db_path)
    init_db(conn)
    box = build_toolbox(settings.db_path, lambda: TODAY, lambda: NORMAL, lambda t: None)
    make_briefing(conn, FakeLLM(_text("Pay the bill.\n- Due Oct 14")), "test-model", box)
    b = c.get("/api/briefing").json()
    assert (b["date"], b["headline"], b["bullets"], b["model"]) == (
        "2026-10-12", "Pay the bill.", ["Due Oct 14"], "test-model")
