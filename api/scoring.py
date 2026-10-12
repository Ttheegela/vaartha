"""News item scoring: TypeSafe Jev (primary) and a deterministic keyword fallback."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
SENTIMENT_LEVELS = (
    "clearly negative",
    "somewhat negative",
    "neutral or mixed",
    "somewhat positive",
    "clearly positive",
)
STRESS_LEVELS = ("none", "localized", "regional or sector-wide", "systemic")
EVENTS = (
    "earnings",
    "guidance",
    "regulation",
    "geopolitical",
    "supply_chain",
    "m&a",
    "macro",
    "other",
)
RETRY_STATUSES = (429, 529)
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0
MAX_TEXT_CHARS = 2000
HTTP_TIMEOUT_SECONDS = 30.0
MARKET_TICKER = "MARKET"
MAX_CONSECUTIVE_FAILURES = 3
HEURISTIC_MODEL = "heuristic-v1"

POSITIVE_WORDS = (
    "beat",
    "surge",
    "record",
    "upgrade",
    "raises",
    "growth",
    "rally",
    "approval",
)
NEGATIVE_WORDS = (
    "miss",
    "plunge",
    "downgrade",
    "cut",
    "lawsuit",
    "ban",
    "sanction",
    "probe",
    "recall",
    "falls",
)
STRESS_RULES = (
    (3, ("war", "invasion", "systemic", "crisis")),
    (2, ("sanction", "tariff", "export control", "embargo")),
    (1, ("strike", "outage", "lawsuit")),
)
EVENT_RULES = (
    ("earnings", ("earnings", "beat", "miss")),
    ("guidance", ("guidance", "outlook")),
    ("regulation", ("regulator", "sec", "ftc", "ban")),
    ("geopolitical", ("sanction", "war", "tariff")),
    ("supply_chain", ("supply", "shortage", "factory")),
    ("m&a", ("acquire", "merger")),
    ("macro", ("fed", "inflation", "rates")),
)
HEURISTIC_CONFIDENCE = 0.5
HEURISTIC_NOISE = 0.1
MATERIAL_NAMED, MATERIAL_OTHER, MATERIAL_MARKET = 0.8, 0.4, 0.5
SENTIMENT_MID_LEVEL = 2
SENTIMENT_CLAMP = 2
MAX_STRESS = 3.0
NEUTRAL_PHRASES = ("rate cut",)  # macro easing, not a negative "cut"


@dataclass(frozen=True)
class ScoreResult:
    """One scored item; sentiment in -1..1, stress as a raw 0..3 score."""

    sentiment: float
    sentiment_conf: float
    material: float
    stress: float
    event: str
    noise: float
    raw: dict
    scored_by: str


class Scorer(Protocol):
    """Anything that can score a news item for a ticker."""

    def score(
        self, title: str, text: str, source: str, ticker: str, company: str
    ) -> ScoreResult | None:
        """Return a ScoreResult, or None if scoring failed."""
        ...


def questions(ticker: str) -> dict:
    """The five scoring questions as TypeSafe JSON."""
    subject = "the overall stock market" if ticker == MARKET_TICKER else "`ticker`"
    market = ticker == MARKET_TICKER
    return {
        "sentiment": {
            "type": "score",
            "instructions": f"How does this item bear on {subject}'s near-term outlook?",
            "criteria": list(SENTIMENT_LEVELS),
        },
        "material": {
            "type": "noul",
            "instructions": (
                "Does `item` contain information that could plausibly move "
                + ("the overall stock market?" if market else "`ticker`'s price?")
            ),
        },
        "stress": {
            "type": "score",
            "instructions": "How much geopolitical or market stress does `item` describe?",
            "criteria": list(STRESS_LEVELS),
        },
        "event": {
            "type": "choice",
            "instructions": "What kind of event is this?",
            "criteria": {e: None for e in EVENTS},
        },
        "noise": {
            "type": "noul",
            "instructions": "Is `item` a joke, meme, or low-information post?",
        },
    }


class TypeSafeScorer:
    """Scores items with TypeSafe Jev; returns None on any failure."""

    def __init__(
        self,
        api_key: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Hold the key privately; the client is built once."""
        self._client = httpx.Client(
            transport=transport,
            timeout=HTTP_TIMEOUT_SECONDS,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        self._sleep = sleep
        self._failures = 0

    def score(
        self, title: str, text: str, source: str, ticker: str, company: str
    ) -> ScoreResult | None:
        """Score one item; after repeated failures stop calling the API (circuit open)."""
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            return None
        result = self._call(title, text, source, ticker, company)
        self._failures = 0 if result else self._failures + 1
        if self._failures == MAX_CONSECUTIVE_FAILURES:
            log.warning("typesafe circuit open")
        return result

    def _call(
        self, title: str, text: str, source: str, ticker: str, company: str
    ) -> ScoreResult | None:
        """Call Jev with retries on 429/529; log status or exception type only."""
        body = {
            "state": {
                "item": {"source": source, "title": title, "text": text[:MAX_TEXT_CHARS]},
                "ticker": ticker,
                "company": company,
            },
            "model": JEV_MODEL,
            "questions": questions(ticker),
        }
        try:
            for attempt in range(MAX_ATTEMPTS):
                resp = self._client.post(TYPESAFE_URL, json=body)
                if resp.status_code in RETRY_STATUSES and attempt < MAX_ATTEMPTS - 1:
                    self._sleep(BACKOFF_SECONDS * 2**attempt)
                    continue
                if resp.status_code >= 400:
                    log.warning("typesafe error %s", resp.status_code)
                    return None
                return self._map(resp.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            log.warning("typesafe failure %s", type(exc).__name__)
        return None

    @staticmethod
    def _map(data: dict) -> ScoreResult:
        """Map a Jev response to a ScoreResult; KeyError if an answer is missing."""
        a = data["answers"]
        return ScoreResult(
            sentiment=max(-1.0, min(1.0, (a["sentiment"]["score"] - SENTIMENT_MID_LEVEL)
                                    / SENTIMENT_CLAMP)),
            sentiment_conf=a["sentiment"]["confidence"],
            material=a["material"]["noul"],
            stress=max(0.0, min(MAX_STRESS, a["stress"]["score"])),
            event=a["event"]["choice"],
            noise=a["noise"]["noul"],
            raw=a,
            scored_by=data["model"],
        )


def _has(text: str, words: tuple[str, ...]) -> bool:
    """True if any word appears as a whole word (optional plural s)."""
    return any(re.search(rf"\b{re.escape(w)}(?:e?s)?\b", text) for w in words)


class HeuristicScorer:
    """Deterministic keyword scorer used when Jev is unavailable."""

    def score(self, title: str, text: str, source: str, ticker: str, company: str) -> ScoreResult:
        """Score by keyword rules over title and text."""
        t = f"{title} {text}".lower()
        sentiment_text = t
        for phrase in NEUTRAL_PHRASES:
            sentiment_text = re.sub(rf"\b{phrase}(?:e?s)?\b", " ", sentiment_text)
        pos = sum(_has(sentiment_text, (w,)) for w in POSITIVE_WORDS)
        neg = sum(_has(sentiment_text, (w,)) for w in NEGATIVE_WORDS)
        level = SENTIMENT_MID_LEVEL + max(-SENTIMENT_CLAMP, min(SENTIMENT_CLAMP, pos - neg))
        if ticker == MARKET_TICKER:
            material = MATERIAL_MARKET
        else:
            names = [n.lower() for n in (ticker, company) if n]
            material = MATERIAL_NAMED if _has(title.lower(), tuple(names)) else MATERIAL_OTHER
        stress = next((lvl for lvl, words in STRESS_RULES if _has(t, words)), 0)
        event = next((e for e, words in EVENT_RULES if _has(t, words)), "other")
        return ScoreResult(
            sentiment=(level - SENTIMENT_MID_LEVEL) / SENTIMENT_CLAMP,
            sentiment_conf=HEURISTIC_CONFIDENCE,
            material=material,
            stress=stress,
            event=event,
            noise=HEURISTIC_NOISE,
            raw={},
            scored_by=HEURISTIC_MODEL,
        )
