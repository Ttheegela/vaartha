"""Encrypt Plaid access tokens at rest (Fernet: AES-128-CBC + HMAC)."""

from cryptography.fernet import Fernet


class TokenBox:
    """Seal and open secrets with one Fernet key."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode())

    def seal(self, token: str) -> bytes:
        """Encrypt a token for storage."""
        return self._fernet.encrypt(token.encode())

    def open(self, blob: bytes) -> str:
        """Decrypt a stored token; raises InvalidToken if the key is wrong."""
        return self._fernet.decrypt(blob).decode()


def new_key() -> str:
    """Generate a new urlsafe base64 Fernet key."""
    return Fernet.generate_key().decode()
