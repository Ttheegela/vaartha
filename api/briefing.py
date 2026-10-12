"""Daily briefing: one agent run with a fixed prompt, stored per date."""

import json
import sqlite3
from datetime import UTC, datetime

from api.agent import EMPTY_ANSWER, build_messages, run_agent
from api.agent_tools import Toolbox

BRIEFING_PROMPT = ("Write today's briefing. First line: the single highest-impact thing to do or "
                   "know today, under 20 words. Then up to 3 lines starting with '- ' giving the "
                   "supporting facts. Cite news as [n:ID].")
MAX_BULLETS = 3
BULLET_MARKERS = ("-", "•")


def parse_briefing(text: str) -> tuple[str, list[str]]:
    """First non-empty line (minus #, * and spaces) is the headline; '-'/'•' lines are bullets."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "", []
    bullets = [ln[1:].strip() for ln in lines[1:] if ln.startswith(BULLET_MARKERS)]
    return lines[0].lstrip("#* ").rstrip("* "), bullets[:MAX_BULLETS]


def make_briefing(conn: sqlite3.Connection, client, model: str, toolbox: Toolbox) -> dict:
    """Run the briefing prompt and store it for today; returns the stored row's fields."""
    done, answer = {}, ""
    for ev in run_agent(client, model, build_messages(toolbox, [], BRIEFING_PROMPT), toolbox):
        if ev["type"] == "answer":
            answer = ev["text"]
        elif ev["type"] == "done":
            done = ev
    if not answer.strip() or answer == EMPTY_ANSWER:
        raise ValueError("empty briefing")
    row = {"date": toolbox.today().isoformat(),
           "items_json": json.dumps({"text": answer, "sources": done.get("sources", [])}),
           "model": model, "generated_at": datetime.now(UTC).isoformat()}
    conn.execute("INSERT OR REPLACE INTO briefings VALUES (:date, :items_json, :model, "
                 ":generated_at)", row)
    conn.commit()
    return row
