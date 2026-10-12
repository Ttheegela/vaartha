CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  access_token_enc BLOB NOT NULL,
  institution TEXT,
  txn_cursor TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  last_synced_at TEXT
);
CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  name TEXT, type TEXT, subtype TEXT, mask TEXT,
  balance_current REAL, balance_available REAL, currency TEXT
);
CREATE TABLE IF NOT EXISTS transactions (
  txn_id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  date TEXT NOT NULL, amount REAL NOT NULL, merchant TEXT,
  pfc_primary TEXT, pfc_detailed TEXT, pending INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_transactions_date ON transactions(date);
CREATE TABLE IF NOT EXISTS securities (
  security_id TEXT PRIMARY KEY, ticker TEXT, name TEXT, type TEXT
);
CREATE TABLE IF NOT EXISTS holdings (
  account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
  security_id TEXT NOT NULL REFERENCES securities(security_id),
  quantity REAL, cost_basis REAL, value REAL, as_of TEXT,
  PRIMARY KEY (account_id, security_id)
);
CREATE TABLE IF NOT EXISTS recurring_streams (
  stream_id TEXT PRIMARY KEY,
  account_id TEXT REFERENCES accounts(account_id) ON DELETE CASCADE,
  direction TEXT NOT NULL CHECK (direction IN ('inflow', 'outflow')),
  kind TEXT NOT NULL CHECK (kind IN ('subscription', 'bill', 'income')),
  merchant TEXT, avg_amount REAL, last_amount REAL, frequency TEXT,
  last_date TEXT, predicted_next_date TEXT, status TEXT, is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS budgets (
  pfc_primary TEXT PRIMARY KEY, monthly_limit REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_amount REAL NOT NULL,
  target_date TEXT, account_ids TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS networth_snapshots (
  date TEXT PRIMARY KEY, assets REAL NOT NULL, liabilities REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS news_items (
  id INTEGER PRIMARY KEY, published_at TEXT, source TEXT NOT NULL, url TEXT,
  title TEXT NOT NULL, text TEXT, tickers TEXT NOT NULL DEFAULT '[]', topics TEXT NOT NULL DEFAULT '[]',
  url_hash TEXT UNIQUE, title_hash TEXT
);
CREATE INDEX IF NOT EXISTS ix_news_title_hash ON news_items(title_hash);
CREATE TABLE IF NOT EXISTS news_scores (
  news_id INTEGER NOT NULL REFERENCES news_items(id) ON DELETE CASCADE,
  ticker TEXT NOT NULL,
  sentiment REAL, sentiment_conf REAL, material REAL, stress REAL, event TEXT, noise REAL,
  raw_json TEXT, scored_at TEXT,
  PRIMARY KEY (news_id, ticker)
);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL,
  action_label TEXT, action_href TEXT, dismissed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS briefings (
  date TEXT PRIMARY KEY, items_json TEXT NOT NULL, model TEXT, generated_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_messages (
  id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT,
  tool_calls TEXT, model TEXT, latency_ms INTEGER, tokens_in INTEGER, tokens_out INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_agent_messages_conv ON agent_messages(conversation_id);
