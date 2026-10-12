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


def test_question_wording_matches_spec():
    from api.scoring import questions

    q = questions("NVDA")
    assert (
        q["sentiment"]["instructions"] == "How does this item bear on `ticker`'s near-term outlook?"
    )
    assert (
        q["material"]["instructions"]
        == "Does `item` contain information that could plausibly move `ticker`'s price?"
    )
    assert (
        q["stress"]["instructions"]
        == "How much geopolitical or market stress does `item` describe?"
    )
    assert q["event"]["instructions"] == "What kind of event is this?"
    assert q["noise"]["instructions"] == "Is `item` a joke, meme, or low-information post?"
    m = questions("MARKET")
    assert (
        m["material"]["instructions"]
        == "Does `item` contain information that could plausibly move the overall stock market?"
    )


def test_circuit_breaker_stops_calling():
    from api.scoring import MAX_ATTEMPTS

    calls = []
    t = httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(429))
    s = TypeSafeScorer("tk", transport=t, sleep=lambda x: None)
    assert [s.score("t", "", "s", "NVDA", "N") for _ in range(5)] == [None] * 5
    assert len(calls) == 3 * MAX_ATTEMPTS
    calls.clear()
    t = httpx.MockTransport(lambda r: calls.append(1) or httpx.Response(401))
    s = TypeSafeScorer("tk", transport=t)
    s.score("t", "", "s", "NVDA", "N")
    assert len(calls) == 1


def test_success_resets_failure_counter():
    codes = iter([500, 500, 200, 500, 500, 200])
    t = httpx.MockTransport(
        lambda r: (lambda c: httpx.Response(c, json=JEV_OK) if c == 200 else httpx.Response(c))(
            next(codes)
        )
    )
    s = TypeSafeScorer("tk", transport=t)
    assert [s.score("t", "", "s", "NVDA", "N") is not None for _ in range(6)] == [
        False,
        False,
        True,
        False,
        False,
        True,
    ]


def test_network_error_and_malformed_return_none():
    def boom(req):
        raise httpx.ConnectError("x")

    assert (
        TypeSafeScorer("tk", transport=httpx.MockTransport(boom)).score("t", "", "s", "NVDA", "N")
        is None
    )
    bad = {"model": "m", "answers": {"sentiment": JEV_OK["answers"]["sentiment"]}}
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=bad))
    assert TypeSafeScorer("tk", transport=t).score("t", "", "s", "NVDA", "N") is None
    t = httpx.MockTransport(lambda r: httpx.Response(200, content=b"not json"))
    assert TypeSafeScorer("tk", transport=t).score("t", "", "s", "NVDA", "N") is None


def test_heuristic_whole_word_and_no_double_count():
    h = HeuristicScorer()
    assert h.score("Bank of X", "", "s", "BAN", "").material == 0.4
    assert h.score("Firm beats", "", "s", "NVDA", "").sentiment == 0.5
