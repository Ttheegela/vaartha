# GeoSentinel Terminal (VARTA)

Regime-Aware Geopolitical Risk Intelligence for Critical Mineral Investors  
Team 7 Lambda · Advanced Python SP2026 · Rutgers University

## Setup

```bash
# 1. Clone and enter repo
cd ~/Desktop/VARTA

# 2. Create virtual environment
python3.12 -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy env template and fill in keys
cp .env.example .env

# 5. Validate environment
python scripts/validate_env.py

# 6. Fetch all data (requires API keys)
python scripts/fetch_all_data.py

# 7. Build demo bundle (run before presentation day)
python scripts/build_demo_bundle.py

# 8. Launch app
streamlit run app.py
```

## Demo Mode (offline)

The app defaults to demo mode (`DEMO_MODE = True` in config.py).  
Run `build_demo_bundle.py` once to generate `data/demo/*.csv` files.  
The full app then works with no internet connection.

## Project Structure

```
VARTA/
├── app.py              Streamlit entry point
├── config.py           All constants — single source of truth
├── src/
│   ├── data/           fetchers · loaders · validators
│   ├── models/         regime · signals · llm · kronos
│   ├── tabs/           tab1–tab5 (display code only)
│   └── utils.py        logger · chart helpers
├── scripts/            fetch_all_data · build_demo_bundle · validate_env
└── data/
    ├── raw/            downloaded source files
    ├── processed/      Parquet files (gitignored)
    └── demo/           offline CSV fallback (gitignored)
```

## Team

Tarun Theegela (Ttheegela) · Sai Raunak Bidesi (ssb196) · Chaitanya Deogaonkar (cmd517) · Satwik Nadipelli (srn91)
