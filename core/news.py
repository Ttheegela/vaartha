"""News text utilities: normalization, dedupe hashes and deterministic tagging."""

import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid")
MIN_TEXT_TICKER_LEN = 3
_PUNCT = re.compile(r"[^\w\s]")
_SPACES = re.compile(r"\s+")
GEO_TOPICS: dict[str, tuple[str, ...]] = {
    "geopolitics": ("sanction", "invasion", "missile", "ceasefire", "tariff", "embargo", "nato",
                    "taiwan", "iran", "ukraine", "russia", "strait of hormuz", "red sea"),
    "energy": ("opec", "brent", "crude", "oil supply", "natural gas"),
    "semiconductors": ("chip", "semiconductor", "export control", "foundry"),
    "macro": ("federal reserve", "rate cut", "rate hike", "inflation", "recession",
              "treasury yield"),
}


@dataclass(frozen=True)
class RawItem:
    """A news item normalized from any source."""

    source: str
    url: str
    title: str
    text: str
    published_at: str
    symbols: tuple[str, ...] = ()


def normalize_title(title: str) -> str:
    """Lowercase, drop punctuation (Unicode-aware), collapse whitespace."""
    return _SPACES.sub(" ", _PUNCT.sub(" ", title.lower())).strip()


def normalize_url(url: str) -> str:
    """Canonical URL: lowercase scheme/host, no tracking params, sorted query,
    no fragment, no trailing slash."""
    parts = urlsplit(url.strip())
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                             if not k.lower().startswith(TRACKING_PREFIXES)))
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def url_hash(url: str) -> str:
    """Dedupe key for a URL."""
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()


def title_hash(title: str) -> str:
    """Dedupe key for a headline."""
    return hashlib.sha1(normalize_title(title).encode()).hexdigest()


def tag_tickers(item: RawItem, securities: dict[str, tuple[str, ...]]) -> list[str]:
    """Tracked tickers this item is about: source symbols first, else text matching."""
    given = [s for s in item.symbols if s in securities]
    if given:
        return sorted(set(given))
    text = f"{item.title} {item.text}"
    lower = text.lower()
    found = set()
    for ticker, aliases in securities.items():
        if len(ticker) >= MIN_TEXT_TICKER_LEN and re.search(
                rf"(?<![\w&./-]){re.escape(ticker)}(?![\w&./-])", text):
            found.add(ticker)
        elif any(re.search(rf"\b{re.escape(a.lower())}\b", lower) for a in aliases):
            found.add(ticker)
    return sorted(found)


def tag_topics(text: str) -> list[str]:
    """Geopolitical/macro topics in the text; keywords match at a word start, optional plural."""
    lower = text.lower()
    return sorted(t for t, kws in GEO_TOPICS.items()
                  if any(re.search(rf"\b{re.escape(k)}s?\b", lower) for k in kws))
