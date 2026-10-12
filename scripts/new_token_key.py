"""Print a fresh TOKEN_ENCRYPTION_KEY line for .env.

Run: uv run python -m scripts.new_token_key >> .env
Losing this key makes stored Plaid tokens unreadable (re-link accounts).
"""

from api.crypto import new_key

if __name__ == "__main__":
    print(f"TOKEN_ENCRYPTION_KEY={new_key()}")
