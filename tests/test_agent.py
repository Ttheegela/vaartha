"""Agent loop against a scripted fake LLM and the seeded toolbox; no network."""

import json
from datetime import UTC, date, datetime
from types import SimpleNamespace as NS

import pytest

from api.agent import (
    FORCE_ANSWER,
    MAX_TOOL_ROUNDS,
    SYSTEM_PROMPT,
    build_messages,
    context_header,
    run_agent,
)
from api.agent_tools import build_toolbox
from api.crypto import TokenBox, new_key
from api.db import connect, init_db
from api.plaid_fake import FakePlaid
from api.settings import Settings
from api.sync import link_item
from core.regime import compute_regime
from scripts.refresh_news import run

TODAY = date(2026, 10, 12)
NORMAL = compute_regime([100.0] * 40, [100.0] * 40, [1800.0] * 40)


def _boom():
    raise RuntimeError("no data")


def _box(path, regime=lambda: NORMAL):
    return build_toolbox(path, lambda: TODAY, regime, lambda t: None)


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "v.db"
    conn = connect(path)
    init_db(conn)
    link_item(conn, FakePlaid(TODAY), TokenBox(new_key()), "public-fake-1", TODAY)
    conn.commit()
    conn.close()
    run(Settings(db_path=path, instance="demo"), offline=True,
        now=datetime(2026, 10, 12, 12, tzinfo=UTC))
    return _box(path)


def _text(content, pin=10, pout=5):
    msg = NS(content=content, tool_calls=None)
    return NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=pin, completion_tokens=pout))


def _tools(*calls, pin=10, pout=5):
    tcs = [NS(id=i, function=NS(name=n, arguments=a)) for i, n, a in calls]
    return NS(choices=[NS(message=NS(content=None, tool_calls=tcs))],
              usage=NS(prompt_tokens=pin, completion_tokens=pout))


class FakeLLM:
    def __init__(self, scripted):
        self.scripted, self.calls = list(scripted), []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.scripted.pop(0)


def test_plain_answer_no_tools(seeded):
    llm = FakeLLM([_text("hello", 7, 3)])
    ev = list(run_agent(llm, "m", [{"role": "user", "content": "hi"}], seeded))
    assert [e["type"] for e in ev] == ["answer", "done"]
    assert ev[0]["text"] == "hello"
    assert ev[1]["tool_calls"] == [] and ev[1]["model"] == "m"
    assert (ev[1]["tokens_in"], ev[1]["tokens_out"]) == (7, 3)


def test_tool_round_then_answer(seeded):
    llm = FakeLLM([_tools(("c1", "get_upcoming_bills", '{"days":7}'), pin=10, pout=2),
                   _text("done", 20, 4)])
    msgs = [{"role": "user", "content": "bills?"}]
    ev = list(run_agent(llm, "m", msgs, seeded))
    assert [e["type"] for e in ev] == ["tool", "answer", "done"]
    assert ev[0] == {"type": "tool", "name": "get_upcoming_bills", "args": {"days": 7}}
    assert ev[2]["tool_calls"] == [{"name": "get_upcoming_bills", "args": {"days": 7}}]
    assert (ev[2]["tokens_in"], ev[2]["tokens_out"]) == (30, 6)
    tool_msg = msgs[-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "c1"
    assert "total" in json.loads(tool_msg["content"])
    assert all("tools" in c for c in llm.calls)


def test_bad_tool_args_reported_to_model(seeded):
    llm = FakeLLM([_tools(("c1", "get_net_worth", "{bad")), _text("ok")])
    msgs = [{"role": "user", "content": "q"}]
    ev = list(run_agent(llm, "m", msgs, seeded))
    assert ev[0]["args"] == {}
    assert "error" in msgs[-1]["content"]
    assert ev[-2]["text"] == "ok"


def test_round_cap_forces_answer(seeded):
    llm = FakeLLM([_tools(("c", "get_net_worth", "{}"))] * MAX_TOOL_ROUNDS + [_text("final")])
    ev = list(run_agent(llm, "m", [{"role": "user", "content": "q"}], seeded))
    assert len(llm.calls) == MAX_TOOL_ROUNDS + 1
    last = llm.calls[-1]
    assert "tools" not in last and last["messages"][-1]["content"] == FORCE_ANSWER
    assert ev[-2]["text"] == "final"


def test_sources_only_for_seen_ids(seeded):
    llm = FakeLLM([_tools(("c", "get_news", "{}")), _text("a [n:5] b [n:999]")])
    class Box:
        specs = []
        def call(self, name, arguments):
            return {"items": [{"id": 5, "title": "T", "source": "S", "published_at": "P"}]}
    ev = list(run_agent(llm, "m", [{"role": "user", "content": "q"}], Box()))
    assert ev[-1]["sources"] == [{"id": 5, "title": "T", "source": "S", "published_at": "P"}]


def test_context_header_survives_failures(tmp_path):
    path = tmp_path / "e.db"
    conn = connect(path)
    init_db(conn)
    conn.close()
    h = context_header(_box(path, _boom))
    assert "regime: unavailable" in h and TODAY.isoformat() in h


def test_context_header_with_data(seeded):
    h = context_header(seeded)
    assert "regime: normal" in h.lower() or NORMAL.label in h
    assert "79481.57" in h


def test_build_messages_order(seeded):
    hist = [{"role": "user", "content": "a", "extra": 1}, {"role": "assistant", "content": "b"}]
    m = build_messages(seeded, hist, "now?")
    assert m[0]["role"] == "system" and m[0]["content"].startswith(SYSTEM_PROMPT)
    assert m[1:] == [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                     {"role": "user", "content": "now?"}]
    assert TODAY.isoformat() in m[0]["content"]
