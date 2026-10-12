"""Run the advisor eval tasks against a live model, or report on saved recordings.

Run: uv run python -m evals.run --model ID --base-url URL [--api-key-env NAME]
         [--price-in USD_PER_MTOK --price-out USD_PER_MTOK] [--only TASK_ID]
     uv run python -m evals.run --report     (re-checks recordings, writes evals/RESULTS.md)
"""

import argparse
import json
import math
import os
import sqlite3
import statistics
import tempfile
from contextlib import closing
from pathlib import Path

import openai

from api.agent import LLM_MAX_RETRIES, LLM_TIMEOUT_SECONDS, build_messages, run_agent
from evals.checks import check_task, load_tasks
from evals.fixture_db import build, eval_toolbox

EVALS_DIR = Path(__file__).parent
RECORDINGS = EVALS_DIR / "recordings"
RESULTS = EVALS_DIR / "RESULTS.md"
TOKENS_PER_MTOK = 1_000_000
P50, P95 = 50, 95


def model_slug(model: str) -> str:
    """Directory name for a model id."""
    return model.replace("/", "_").replace(":", "_")


def percentile(values: list[float], pct: int) -> float:
    """Nearest-rank percentile of a non-empty list."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def run_task(client, model: str, toolbox, task: dict) -> dict:
    """Run one task as a fresh conversation; returns the recording without expected_pass."""
    answer, done = "", {}
    for ev in run_agent(client, model, build_messages(toolbox, [], task["question"]), toolbox):
        if ev["type"] == "answer":
            answer = ev["text"]
        elif ev["type"] == "done":
            done = ev
    return {"task_id": task["id"], "model": model, "answer": answer,
            "tool_calls": done["tool_calls"], "sources": done["sources"],
            "latency_ms": done["latency_ms"], "tokens_in": done["tokens_in"],
            "tokens_out": done["tokens_out"]}


def run_live(args) -> None:
    """Run the selected tasks against the model and write one recording per task."""
    client = openai.OpenAI(base_url=args.base_url, timeout=LLM_TIMEOUT_SECONDS,
                           api_key=os.environ.get(args.api_key_env or "") or "unused",
                           max_retries=LLM_MAX_RETRIES)
    tasks = [t for t in load_tasks() if args.only in (None, t["id"])]
    out_dir = RECORDINGS / model_slug(args.model)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        db = build(Path(tmp) / "fixture.db")
        toolbox = eval_toolbox(db)
        with closing(sqlite3.connect(db)) as conn:
            for task in tasks:
                rec = run_task(client, args.model, toolbox, task)
                rec["cost_usd"] = (rec["tokens_in"] * args.price_in
                                   + rec["tokens_out"] * args.price_out) / TOKENS_PER_MTOK
                fails = check_task(task, rec, conn)
                rec["expected_pass"] = not fails
                (out_dir / f"{task['id']}.json").write_text(json.dumps(rec, indent=2))
                print(f"{'PASS' if not fails else 'FAIL'} {task['id']}")
                for f in fails:
                    print(f"     - {f}")


def report() -> str:
    """Markdown report: a stats table per model, then the task x model pass matrix."""
    tasks = load_tasks()
    known = {t["id"] for t in tasks}
    recs: dict[str, dict[str, dict]] = {}
    for f in sorted(RECORDINGS.glob("*/*.json")):
        r = json.loads(f.read_text())
        if r["task_id"] not in known:  # task was removed from tasks.yaml
            continue
        recs.setdefault(r["model"], {})[r["task_id"]] = r
    if not recs:
        return "# Eval results\n\nNo runs recorded yet.\n"
    passed: dict[str, dict[str, bool]] = {m: {} for m in recs}
    with tempfile.TemporaryDirectory() as tmp, \
            closing(sqlite3.connect(build(Path(tmp) / "fixture.db"))) as conn:
        by_id = {t["id"]: t for t in tasks}
        for m, rs in recs.items():
            passed[m] = {i: not check_task(by_id[i], r, conn) for i, r in rs.items()}
    lines = ["# Eval results", ""]
    for m, rs in recs.items():
        lat = [r["latency_ms"] for r in rs.values()]
        n, ok = len(tasks), sum(passed[m].values())
        lines += [f"## {m}", "",
                  "| recorded | passed | pass rate | p50 latency ms | p95 latency ms "
                  "| mean tokens in | mean tokens out | total cost USD |",
                  "|---|---|---|---|---|---|---|---|",
                  f"| {len(rs)}/{n} | {ok} | {ok / n:.0%} | {percentile(lat, P50):.0f} "
                  f"| {percentile(lat, P95):.0f} "
                  f"| {statistics.mean(r['tokens_in'] for r in rs.values()):.0f} "
                  f"| {statistics.mean(r['tokens_out'] for r in rs.values()):.0f} "
                  f"| {sum(r.get('cost_usd', 0) for r in rs.values()):.4f} |", ""]
    models = list(recs)
    lines += ["## Pass matrix", "", "| task | " + " | ".join(models) + " |",
              "|---|" + "---|" * len(models)]
    for t in tasks:
        cells = [("✓" if passed[m][t["id"]] else "✗") if t["id"] in passed[m] else "–"
                 for m in models]
        lines.append(f"| {t['id']} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    """CLI entry point."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--model")
    p.add_argument("--base-url")
    p.add_argument("--api-key-env", help="name of the env var holding the API key")
    p.add_argument("--price-in", type=float, default=0.0, help="USD per million input tokens")
    p.add_argument("--price-out", type=float, default=0.0, help="USD per million output tokens")
    p.add_argument("--only", help="run a single task id")
    p.add_argument("--report", action="store_true", help="write evals/RESULTS.md from recordings")
    args = p.parse_args()
    if args.report:
        RESULTS.write_text(report())
        print(f"wrote {RESULTS}")
    elif args.model and args.base_url:
        run_live(args)
    else:
        p.error("--model and --base-url are required unless --report")


if __name__ == "__main__":
    main()
