"""Deterministic checks of a recorded advisor answer against the fixture database."""

import json
import re
import sqlite3
from pathlib import Path

import yaml

from api.agent import CITATION_RE
from api.briefing import BRIEFING_PROMPT

TASKS_FILE = Path(__file__).with_name("tasks.yaml")
BRIEFING_SENTINEL = "BRIEFING_PROMPT"
ABS_TOL = 0.5
DEFAULT_REL = 0.01
NUMBER_RE = re.compile(r"(?<!\d)(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
NOISE_RE = re.compile(
    r"\[n:\d+\]|\d{4}-\d{2}-\d{2}"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? \d{1,2}\b")
CAPS_RE = re.compile(r"\b[A-Z]{2,5}\b")
AMOUNT_RE = re.compile(r"\$\s?\d")
ALLOWED_CAPS = frozenset(
    "US USD ETF APR APY CPI GDP FOMC FED AI OK IRA LLC SEC EPS YTD ATM FDIC CEO NYSE NASDAQ "
    "PM AM EST ET TV NOTE ALL MARKET GPU ACH HYSA VIX IPO EV TLDR".split())


def load_tasks(path: Path = TASKS_FILE) -> list[dict]:
    """Tasks from the YAML file, with the BRIEFING_PROMPT sentinel resolved."""
    tasks = yaml.safe_load(path.read_text())
    for t in tasks:
        if t["question"] == BRIEFING_SENTINEL:
            t["question"] = BRIEFING_PROMPT
    return tasks


def parse_numbers(text: str) -> list[float]:
    """Magnitudes of the numbers in the text; `$`, commas, `%`, signs, dates and `[n:ID]` dropped."""
    cleaned = NOISE_RE.sub(" ", text)
    return [float(m.replace(",", "")) for m in NUMBER_RE.findall(cleaned)]


def _db_tickers(conn: sqlite3.Connection) -> set[str]:
    found = {r[0] for r in conn.execute("SELECT ticker FROM securities") if r[0]}
    caps_sources = [r[0] for r in conn.execute("SELECT name FROM securities")]
    caps_sources += [r[0] for r in conn.execute("SELECT title FROM news_items")]
    for text in caps_sources:
        found.update(CAPS_RE.findall(text or ""))
    for (raw,) in conn.execute("SELECT tickers FROM news_items"):
        found.update(json.loads(raw))
    return found


def check_task(task: dict, rec: dict, conn: sqlite3.Connection) -> list[str]:
    """Failure messages for one recording against its task; empty means pass."""
    answer, fails = rec["answer"], []
    called = {c["name"] for c in rec["tool_calls"]}
    fails += [f"tool not called: {t}" for t in task.get("tools", []) if t not in called]

    nums = parse_numbers(answer)
    for spec in task.get("numbers", []):
        v = conn.execute(spec["sql"]).fetchone()[0]
        if v is None:
            fails.append(f"ground truth is null: {spec['sql']}")
            continue
        tol = max(spec.get("rel", DEFAULT_REL) * abs(v), ABS_TOL)
        if not any(abs(n - v) <= tol for n in nums):
            fails.append(f"expected a number near {v}")

    # question words are allowed so an answer may echo the user's own ticker
    allowed = ALLOWED_CAPS | _db_tickers(conn) | set(CAPS_RE.findall(task["question"]))
    fails += [f"unknown ticker: {t}" for t in sorted(set(CAPS_RE.findall(answer)) - allowed)]

    cited = [int(i) for i in CITATION_RE.findall(answer)]
    known = {r[0] for r in conn.execute("SELECT id FROM news_items")}
    sources = {s["id"] for s in rec["sources"]}
    fails += [f"citation [n:{i}] not in news_items" for i in cited if i not in known]
    fails += [f"citation [n:{i}] not in sources" for i in cited if i in known and i not in sources]
    if task.get("cite") and not cited:
        fails.append("no citation")

    if task.get("no_amounts") and AMOUNT_RE.search(answer):
        fails.append("answer contains a $ amount")
    plain = answer.replace("\u2019", "'")
    fails += [f"forbidden text: {f}" for f in task.get("forbid", [])
              if re.search(f, plain, re.IGNORECASE)]
    return fails
