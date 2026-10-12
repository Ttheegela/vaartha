"""Jev request/response mapping, retries, failures; heuristic determinism."""

import json

import httpx

from api.scoring import JEV_MODEL, TYPESAFE_URL, HeuristicScorer, TypeSafeScorer

JEV_OK = {
    "model": "jev-1",
    "answers": {
        "sentiment": {
            "type": "score",
            "score": 3.0,
            "confidence": 0.8,
            "probabilities": {},
            "legend": {},
        },
        "material": {"type": "noul", "noul": 0.9},
        "stress": {
            "type": "score",
            "score": 1.4,
            "confidence": 0.6,
            "probabilities": {},
            "legend": {},
        },
        "event": {"type": "choice", "choice": "earnings", "confidence": 0.7, "probabilities": {}},
        "noise": {"type": "noul", "noul": 0.05},
    },
    "usage": {"input_tokens": 300, "output_tokens": 0},
}


def test_request_shape_and_mapping():
    seen = {}

    def h(req):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=JEV_OK)

    r = TypeSafeScorer("tk", transport=httpx.MockTransport(h)).score(
        "NVIDIA beats", "x" * 5000, "Alpaca/benzinga", "NVDA", "NVIDIA"
    )
    assert seen["url"] == TYPESAFE_URL and seen["auth"] == "Bearer tk"
    assert seen["body"]["model"] == JEV_MODEL
    assert set(seen["body"]["questions"]) == {"sentiment", "material", "stress", "event", "noise"}
    assert seen["body"]["questions"]["sentiment"]["type"] == "score"
    assert len(seen["body"]["questions"]["sentiment"]["criteria"]) == 5
    assert len(seen["body"]["state"]["item"]["text"]) == 2000
    assert (r.sentiment, r.sentiment_conf, r.material, r.stress, r.event, r.noise) == (
        0.5,
        0.8,
        0.9,
        1.4,
        "earnings",
        0.05,
    )
    assert r.scored_by == "jev-1"


def test_retries_then_succeeds():
    calls, sleeps = [], []

    def h(req):
        calls.append(1)
        return httpx.Response(529) if len(calls) < 3 else httpx.Response(200, json=JEV_OK)

    r = TypeSafeScorer("tk", transport=httpx.MockTransport(h), sleep=sleeps.append).score(
        "t", "", "s", "NVDA", "NVIDIA"
    )
    assert r is not None and len(calls) == 3 and sleeps == [1.0, 2.0]


def test_gives_up_returns_none():
    always = httpx.MockTransport(lambda r: httpx.Response(429))
    assert (
        TypeSafeScorer("tk", transport=always, sleep=lambda s: None).score(
            "t", "", "s", "NVDA", "N"
        )
        is None
    )
    unauth = httpx.MockTransport(lambda r: httpx.Response(401, json={"error": "bad key"}))
    assert TypeSafeScorer("bad", transport=unauth).score("t", "", "s", "NVDA", "N") is None


def test_market_pseudo_ticker_instruction():
    seen = {}

    def h(req):
        seen["q"] = json.loads(req.content)["questions"]["sentiment"]["instructions"]
        return httpx.Response(200, json=JEV_OK)

    TypeSafeScorer("tk", transport=httpx.MockTransport(h)).score(
        "Fed cuts", "", "RSS", "MARKET", ""
    )
    assert "overall stock market" in seen["q"]


def test_heuristic_is_deterministic():
    h = HeuristicScorer()
    a = h.score("NVIDIA beats estimates, record growth", "", "x", "NVDA", "NVIDIA")
    assert a == h.score("NVIDIA beats estimates, record growth", "", "x", "NVDA", "NVIDIA")
    assert (
        a.sentiment == 1.0
        and a.event == "earnings"
        and a.material == 0.8
        and a.scored_by == "heuristic-v1"
    )
    b = h.score("US expands chip export controls and sanctions", "", "x", "MARKET", "")
    assert b.sentiment < 0 and b.stress == 2 and b.event == "geopolitical"
