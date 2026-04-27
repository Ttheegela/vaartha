"""
validate_env.py — GeoSentinel Terminal (VARTA)
Check Ollama availability, API key presence, and dependency versions.
Run this on each team member's machine before starting development.
Usage: python scripts/validate_env.py
"""

import sys
import requests
from src.utils import log
from config import (
    OLLAMA_HOST, OLLAMA_DEEP_MODEL, OLLAMA_FAST_MODEL,
    FRED_API_KEY, TIINGO_API_KEY, FINNHUB_API_KEY,
)


def check_python():
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 12
    status = "OK" if ok else "WARN (need 3.12+)"
    log.info(f"Python {v.major}.{v.minor}.{v.micro} — {status}")


def check_ollama():
    try:
        resp = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        for model in [OLLAMA_DEEP_MODEL, OLLAMA_FAST_MODEL]:
            status = "OK" if any(model in m for m in models) else f"MISSING — run: ollama pull {model}"
            log.info(f"Ollama {model} — {status}")
    except Exception as e:
        log.warning(f"Ollama not reachable at {OLLAMA_HOST}: {e}")


def check_api_keys():
    keys = {
        "FRED_API_KEY":   FRED_API_KEY,
        "TIINGO_API_KEY": TIINGO_API_KEY,
        "FINNHUB_API_KEY":FINNHUB_API_KEY,
    }
    for name, val in keys.items():
        status = "OK" if val else "MISSING (set in .env)"
        log.info(f"{name} — {status}")


def check_imports():
    packages = [
        ("streamlit",  "streamlit"),
        ("polars",     "polars"),
        ("duckdb",     "duckdb"),
        ("plotly",     "plotly"),
        ("folium",     "folium"),
        ("yfinance",   "yfinance"),
        ("fredapi",    "fredapi"),
        ("xgboost",    "xgboost"),
        ("hmmlearn",   "hmmlearn"),
        ("sklearn",    "scikit-learn"),
        ("torch",      "torch"),
    ]
    for import_name, pkg_name in packages:
        try:
            __import__(import_name)
            log.info(f"{pkg_name} — OK")
        except ImportError:
            log.warning(f"{pkg_name} — MISSING (pip install {pkg_name})")


def main():
    log.info("=== validate_env.py ===")
    check_python()
    check_imports()
    check_ollama()
    check_api_keys()
    log.info("=== validation complete ===")


if __name__ == "__main__":
    main()
