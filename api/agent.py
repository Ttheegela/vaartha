"""Hand-written advisor tool loop over an OpenAI-compatible chat endpoint."""

import json
import re
import time
from collections.abc import Callable, Iterator

import openai

from api.agent_tools import Toolbox
from api.settings import Settings

MAX_TOOL_ROUNDS = 8
LLM_TIMEOUT_SECONDS = 45  # under Heroku's 55 s idle window on the SSE stream
LLM_MAX_RETRIES = 1
BILLS_WINDOW_DAYS = 7
MS_PER_SECOND = 1000
CITATION_RE = re.compile(r"\[n:(\d+)\]")
FORCE_ANSWER = "Answer now using only the data you already have."
UNAVAILABLE = "unavailable"
EMPTY_ANSWER = "I couldn't put together an answer from the data. Please try rephrasing."

SYSTEM_PROMPT = """You are Vārtā, a personal finance and investing assistant for one person.
Rules:
- Look things up with the tools. Every number you state must come from a tool result in this conversation.
- When you mention a news story, cite it as [n:ID] with the id from get_news.
- If the data you need is missing, say so plainly. Never estimate a balance, price or amount.
- You cannot move money, trade, or change anything. Say so if asked.
- Lead with the answer, then at most three short supporting points.
This is educational information, not financial advice."""  # noqa: E501


def llm_client(settings: Settings) -> openai.OpenAI:
    """OpenAI-compatible client for OpenRouter or Ollama from settings."""
    return openai.OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "unused",
                         timeout=LLM_TIMEOUT_SECONDS, max_retries=LLM_MAX_RETRIES)


def context_header(toolbox: Toolbox) -> str:
    """Today, regime, net worth and bills due soon; failed lookups render as unavailable."""
    regime = toolbox.call("get_market_regime", {})
    net = toolbox.call("get_net_worth", {})
    bills = toolbox.call("get_upcoming_bills", {"days": BILLS_WINDOW_DAYS})
    regime_s = UNAVAILABLE if "error" in regime else regime.get("label", UNAVAILABLE)
    net_s = (UNAVAILABLE if "error" in net else
             "no accounts linked" if not net.get("accounts") else f"{net.get('net')}")
    bills_s = (UNAVAILABLE if "error" in bills
               else f"{len(bills['items'])} totaling {bills['total']}")
    return (f"Today: {toolbox.today().isoformat()}\nregime: {regime_s}\n"
            f"net worth: {net_s}\nbills due in next {BILLS_WINDOW_DAYS} days: {bills_s}")


def build_messages(toolbox: Toolbox, history: list[dict], question: str) -> list[dict]:
    """System prompt plus context header, prior turns, then the new question."""
    return [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{context_header(toolbox)}"},
            *({"role": h["role"], "content": h["content"]} for h in history),
            {"role": "user", "content": question}]


def _safe_args(arguments: str) -> dict:
    try:
        parsed = json.loads(arguments)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _source(item: dict) -> dict:
    return {k: item.get(k) for k in ("id", "title", "source", "published_at")}


def run_agent(client, model: str, messages: list[dict], toolbox: Toolbox,
              clock: Callable[[], float] = time.monotonic) -> Iterator[dict]:
    """Call the model, run requested tools, repeat; at most MAX_TOOL_ROUNDS tool rounds."""
    start, calls, seen, tin, tout = clock(), [], {}, 0, 0
    answer = ""
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        final = round_no == MAX_TOOL_ROUNDS
        if final:
            messages.append({"role": "user", "content": FORCE_ANSWER})
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=toolbox.specs,
            **({"tool_choice": "none"} if final else {}))
        if resp.usage:
            tin, tout = tin + resp.usage.prompt_tokens, tout + resp.usage.completion_tokens
        msg = resp.choices[0].message
        if final or not msg.tool_calls:
            answer = (msg.content or "").strip() and msg.content or EMPTY_ANSWER
            break
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            args = _safe_args(tc.function.arguments)
            yield {"type": "tool", "name": tc.function.name, "args": args}
            calls.append({"name": tc.function.name, "args": args})
            result = toolbox.call(tc.function.name, tc.function.arguments)
            if tc.function.name == "get_news":
                seen.update({i["id"]: i for i in result.get("items", [])})
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, separators=(",", ":"))})
    cited = dict.fromkeys(int(m) for m in CITATION_RE.findall(answer))
    yield {"type": "answer", "text": answer}
    yield {"type": "done", "tool_calls": calls, "model": model,
           "sources": [_source(seen[i]) for i in cited if i in seen],
           "tokens_in": tin, "tokens_out": tout,
           "latency_ms": round((clock() - start) * MS_PER_SECOND)}
