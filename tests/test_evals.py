"""Eval harness: deterministic checks, fixture DB, task file and recorded-response replay."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.briefing import BRIEFING_PROMPT
from evals.checks import check_task, load_tasks, parse_numbers
from evals.fixture_db import build, eval_toolbox

RECORDINGS = Path(__file__).resolve().parent.parent / "evals" / "recordings"
REQUIRED_KEYS = {"id", "question"}
TASK_COUNT = 25


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    path = build(tmp_path_factory.mktemp("evals") / "fixture.db")
    with closing(sqlite3.connect(path)) as c:
        yield c


def _news_id(conn) -> int:
    return conn.execute("SELECT id FROM news_items ORDER BY id LIMIT 1").fetchone()[0]


def _rec(answer, tools=("get_upcoming_bills",), sources=()):
    return {"answer": answer, "tool_calls": [{"name": t, "args": {}} for t in tools],
            "sources": [{"id": i} for i in sources]}


TASK = {"id": "t", "question": "q", "tools": ["get_upcoming_bills"],
        "numbers": [{"sql": "SELECT 207.42"}]}


def test_parse_numbers():
    text = "Paid $2,450.00, balance -1,240.55, up 86%, rate 11.58 or $96."
    assert parse_numbers(text) == [2450.0, -1240.55, 86.0, 11.58, 96.0]
    assert parse_numbers("none here") == []


def test_check_pass(conn):
    assert check_task(TASK, _rec("You owe $207.42 this week."), conn) == []


def test_missing_tool(conn):
    out = check_task(TASK, _rec("$207.42", tools=("get_goals",)), conn)
    assert any("get_upcoming_bills" in m for m in out)


def test_wrong_number(conn):
    assert check_task(TASK, _rec("You owe $300."), conn)


def test_null_ground_truth(conn):
    task = {**TASK, "numbers": [{"sql": "SELECT NULL"}]}
    assert any("ground truth is null" in m for m in check_task(task, _rec("$1"), conn))


def test_invented_ticker(conn):
    out = check_task({"id": "t", "question": "q"}, _rec("Buy ZZZZ and NVDA."), conn)
    assert any("ZZZZ" in m for m in out) and not any("NVDA" in m for m in out)


def test_citations(conn):
    nid = _news_id(conn)
    task = {"id": "t", "question": "q", "cite": True}
    assert check_task(task, _rec(f"News [n:{nid}]", sources=[nid]), conn) == []
    assert check_task(task, _rec("[n:99999]", sources=[99999]), conn)  # unknown id
    assert check_task(task, _rec(f"[n:{nid}]", sources=[]), conn)  # not in sources
    assert check_task(task, _rec("no citation"), conn)  # cite required


def test_no_amounts_and_forbid(conn):
    assert check_task({"id": "t", "question": "q", "no_amounts": True}, _rec("It is $ 5."), conn)
    assert check_task({"id": "t", "question": "q", "forbid": ["Done"]}, _rec("all done"), conn)


def test_build_is_deterministic(tmp_path):
    counts = []
    for n in range(2):
        with closing(sqlite3.connect(build(tmp_path / f"{n}.db"))) as c:
            counts.append((c.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
                           [r[0] for r in c.execute("SELECT id FROM news_items ORDER BY id")]))
    assert counts[0] == counts[1] and counts[0][0] > 0


def test_tasks_file(conn):
    tasks = load_tasks()
    assert len(tasks) == TASK_COUNT
    assert len({t["id"] for t in tasks}) == TASK_COUNT
    assert all(REQUIRED_KEYS <= set(t) for t in tasks)
    assert next(t for t in tasks if t["id"] == "daily-briefing")["question"] == BRIEFING_PROMPT
    for t in tasks:
        for n in t.get("numbers", []):
            assert conn.execute(n["sql"]).fetchone()[0] is not None, t["id"]


def test_replay_recordings(conn):
    files = sorted(RECORDINGS.glob("*/*.json"))
    if not files:
        pytest.skip("no recordings yet")
    tasks = {t["id"]: t for t in load_tasks()}
    for f in files:
        rec = json.loads(f.read_text())
        passed = not check_task(tasks[rec["task_id"]], rec, conn)
        assert passed == rec["expected_pass"], f


class _FakeClient:
    """Answers immediately with a fixed reply (no tool calls)."""

    def __init__(self, text):
        msg = SimpleNamespace(content=text, tool_calls=None)
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5)
        self.chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **_: SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                                               usage=usage)))


def test_run_task_and_report(tmp_path, monkeypatch, conn):
    from evals import run

    task = next(t for t in load_tasks() if t["id"] == "refuse-transfer")
    rec = run.run_task(_FakeClient("I can't move money."), "m/x:1", eval_toolbox(
        Path(conn.execute("PRAGMA database_list").fetchone()[2])), task)
    assert rec["answer"] == "I can't move money." and rec["tokens_in"] == 10
    monkeypatch.setattr(run, "RECORDINGS", tmp_path)
    assert "No runs recorded yet" in run.report()
    (tmp_path / "m_x_1").mkdir()
    (tmp_path / "m_x_1" / "refuse-transfer.json").write_text(json.dumps(rec))
    text = run.report()
    assert "| 1 | 1 | 100% |" in text and "| refuse-transfer | ✓ |" in text
