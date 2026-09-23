# Upgrade v1 scaffold — offline regime demo + feed hooks

**Status:** landed on branch `upgrade/v1-scaffold` (offline-first).  
**Live GPR / MRI:** deferred (stubs raise `NotImplementedError`).

## What landed

| Path | Role |
|------|------|
| `src/regime/offline_demo.py` | Fixture load → regime labels → change-point stub → JSON summary |
| `src/regime/feeds.py` | `FeedConfig(offline_mode=True)`, `fetch_gpr()` / `fetch_mri()` hooks |
| `data/fixtures/regime_events.json` | 8 fake-but-plausible geo/market events with `source_url` / `evidence_urls` |
| `scripts/run_offline_regime_demo.py` | One-liner runner (imports offline demo only) |

## Run (no network, no paid APIs)

```bash
python scripts/run_offline_regime_demo.py
# or
python -m src.regime.offline_demo
```

## Explicitly deferred

- Live **Caldara–Iacoviello GPR** ingest (`fetch_gpr`)
- Live **MRI / moneyfeel-style** feeds (`fetch_mri`)
- LLM validation path (`llm_validate(..., use_llm=True)` → NotImplemented)

Existing Streamlit `app.py` is **unchanged** in this scaffold.
