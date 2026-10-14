"""Passkey (WebAuthn) lock for the owner instance: setup code, ceremonies, sessions, middleware.

Only one person uses the owner instance, so there are no user accounts: any registered passkey
unlocks it. Registering a passkey always needs a fresh one-time setup code from the CLI
(`python -m scripts.passkey setup-code`). Tokens, challenges and codes are never logged.
"""

import hashlib
import hmac
import json
import secrets
import sqlite3
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import (
    base64url_to_bytes,
    bytes_to_base64url,
    parse_authentication_credential_json,
    parse_client_data_json,
    parse_registration_credential_json,
)
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from api.db import connect
from api.settings import Settings

SESSION_COOKIE = "varta_session"
AUTH_MAX_HOURS = 12  # absolute session lifetime, however active
SETUP_CODE_MINUTES = 10
SETUP_CODE_LENGTH = 8
SETUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no I/L/O/0/1
CHALLENGE_SECONDS = 300
TOKEN_BYTES = 32
USER_HANDLE_BYTES = 16
SETUP_CODE_KEY = "auth:setup_code"
USER_HANDLE_KEY = "auth:user_handle"
USER_NAME = "owner"
PUBLIC_PREFIX = "/api/auth/"  # the only paths reachable while locked, plus OPEN_PATHS
OPEN_PATHS = frozenset({"/healthz"})
KIND_REGISTER, KIND_LOGIN = "register", "login"
# parse/verify failures: py_webauthn's own, our challenge/credential lookups, bad base64/JSON
CEREMONY_ERRORS = (WebAuthnException, LookupError, ValueError, TypeError)
LOCKED = {"detail": "locked"}


def _now() -> datetime:
    """Current UTC time (tests replace this)."""
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    """Fixed-width ISO UTC string, so stored times also compare correctly as text."""
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _verify_registration(**kw):
    """py_webauthn registration verification (test seam)."""
    return verify_registration_response(**kw)


def _verify_authentication(**kw):
    """py_webauthn authentication verification (test seam)."""
    return verify_authentication_response(**kw)


# --- setup code -------------------------------------------------------------------------

def _normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch not in "- ")


def issue_setup_code(db_path: Path) -> str:
    """Store the sha256 of a new one-time code (replacing any old one); return it as XXXX-XXXX."""
    code = "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(SETUP_CODE_LENGTH))
    expires = _now() + timedelta(minutes=SETUP_CODE_MINUTES)
    value = json.dumps({"sha256": _sha256(code), "expires_at": _iso(expires)})
    with closing(connect(db_path)) as conn, conn:
        conn.execute("INSERT OR REPLACE INTO app_state (key, value) VALUES (?, ?)",
                     (SETUP_CODE_KEY, value))
    half = SETUP_CODE_LENGTH // 2
    return f"{code[:half]}-{code[half:]}"


def _setup_code_valid(conn: sqlite3.Connection, code: str) -> str | None:
    """The stored row value if `code` matches the unexpired setup code, else None."""
    row = conn.execute("SELECT value FROM app_state WHERE key=?", (SETUP_CODE_KEY,)).fetchone()
    if row is None:
        return None
    stored = json.loads(row["value"])
    match = hmac.compare_digest(_sha256(_normalize_code(code)), stored["sha256"])
    if not match or _now() >= datetime.fromisoformat(stored["expires_at"]):
        return None
    return row["value"]


def _consume_setup_code(conn: sqlite3.Connection, code: str) -> bool:
    """Check and delete the setup code in one statement; True only for the single winner."""
    value = _setup_code_valid(conn, code)
    if value is None:
        return False
    cur = conn.execute("DELETE FROM app_state WHERE key=? AND value=?", (SETUP_CODE_KEY, value))
    conn.commit()
    return cur.rowcount == 1


# --- challenges -----------------------------------------------------------------------

def _store_challenge(conn: sqlite3.Connection, challenge: bytes, kind: str) -> None:
    now = _now()
    with conn:
        conn.execute("DELETE FROM auth_challenges WHERE expires_at <= ?", (_iso(now),))
        conn.execute("INSERT INTO auth_challenges (challenge, kind, expires_at) VALUES (?, ?, ?)",
                     (bytes_to_base64url(challenge), kind,
                      _iso(now + timedelta(seconds=CHALLENGE_SECONDS))))


def _consume_challenge(conn: sqlite3.Connection, client_data_json: bytes, kind: str) -> bytes:
    """Delete the challenge the client signed; raise unless it was ours, unused and unexpired."""
    challenge = parse_client_data_json(client_data_json).challenge
    with conn:
        cur = conn.execute("DELETE FROM auth_challenges WHERE challenge=? AND kind=? "
                           "AND expires_at > ?", (bytes_to_base64url(challenge), kind,
                                                  _iso(_now())))
    if cur.rowcount != 1:
        raise LookupError("unknown, used or expired challenge")
    return challenge


# --- sessions -------------------------------------------------------------------------

def _create_session(conn: sqlite3.Connection) -> str:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    now = _iso(_now())
    with conn:
        conn.execute("INSERT INTO auth_sessions (token_hash, created_at, last_seen_at) "
                     "VALUES (?, ?, ?)", (_sha256(token), now, now))
    return token


def check_session(db_path: Path, token: str | None, idle_minutes: int, touch: bool) -> bool:
    """True if `token` names a live session; expired sessions are deleted. `touch` slides it."""
    if not token:
        return False
    token_hash, now = _sha256(token), _now()
    with closing(connect(db_path)) as conn, conn:
        row = conn.execute("SELECT created_at, last_seen_at FROM auth_sessions "
                           "WHERE token_hash=?", (token_hash,)).fetchone()
        if row is None:
            return False
        idle = now - datetime.fromisoformat(row["last_seen_at"])
        age = now - datetime.fromisoformat(row["created_at"])
        if idle >= timedelta(minutes=idle_minutes) or age >= timedelta(hours=AUTH_MAX_HOURS):
            conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (token_hash,))
            return False
        if touch:
            conn.execute("UPDATE auth_sessions SET last_seen_at=? WHERE token_hash=?",
                         (_iso(now), token_hash))
        return True


def _set_session_cookie(resp: Response, token: str, settings: Settings) -> None:
    """Session cookie (no Max-Age): the server enforces idle and absolute expiry."""
    resp.set_cookie(SESSION_COOKIE, token, path="/", httponly=True, samesite="strict",
                    secure=settings.passkey_origin.startswith("https://"))


# --- router ---------------------------------------------------------------------------

class StatusOut(BaseModel):
    """Lock state for the web app."""

    auth_required: bool
    authenticated: bool
    has_credentials: bool


class SetupCodeIn(BaseModel):
    """One-time setup code from the CLI."""

    setup_code: str


class RegisterVerifyIn(BaseModel):
    """Setup code plus the browser's navigator.credentials.create() result (JSON)."""

    setup_code: str
    credential: dict


class LoginVerifyIn(BaseModel):
    """The browser's navigator.credentials.get() result (JSON)."""

    credential: dict


class OkOut(BaseModel):
    """Unlocked."""

    ok: bool = True


def _user_handle(conn: sqlite3.Connection) -> bytes:
    """Fixed per-instance WebAuthn user.id, generated once."""
    with conn:
        conn.execute("INSERT OR IGNORE INTO app_state (key, value) VALUES (?, ?)",
                     (USER_HANDLE_KEY, bytes_to_base64url(secrets.token_bytes(USER_HANDLE_BYTES))))
    row = conn.execute("SELECT value FROM app_state WHERE key=?", (USER_HANDLE_KEY,)).fetchone()
    return base64url_to_bytes(row["value"])


def _transports(raw: str | None) -> list[AuthenticatorTransport] | None:
    if not raw:
        return None
    return [AuthenticatorTransport(t) for t in json.loads(raw)
            if t in AuthenticatorTransport._value2member_map_]


def build_auth_router(settings: Settings) -> APIRouter:
    """/api/auth/*: status always; the ceremonies only when the owner lock is on (else 404)."""
    router = APIRouter(prefix="/api/auth")
    db_path = settings.db_path

    def require_lock() -> None:
        if not settings.auth_required:
            raise HTTPException(status_code=404, detail="auth not enabled")

    def ok_with_session(conn: sqlite3.Connection) -> Response:
        resp = JSONResponse(OkOut().model_dump())
        _set_session_cookie(resp, _create_session(conn), settings)
        return resp

    @router.get("/status", response_model=StatusOut)
    def status(request: Request) -> StatusOut:
        """Whether the lock is on, this browser is unlocked, and any passkey exists."""
        with closing(connect(db_path)) as conn:
            n = conn.execute("SELECT COUNT(*) FROM auth_credentials").fetchone()[0]
        authed = settings.auth_required and check_session(
            db_path, request.cookies.get(SESSION_COOKIE), settings.auth_idle_minutes, touch=False)
        return StatusOut(auth_required=settings.auth_required, authenticated=authed,
                         has_credentials=n > 0)

    @router.post("/register/options")
    def register_options(body: SetupCodeIn) -> Response:
        """PublicKeyCredentialCreationOptions; needs a valid setup code (403 otherwise)."""
        require_lock()
        with closing(connect(db_path)) as conn:
            if _setup_code_valid(conn, body.setup_code) is None:
                raise HTTPException(status_code=403, detail="invalid or expired setup code")
            existing = conn.execute("SELECT credential_id, transports FROM auth_credentials")
            exclude = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(r["credential_id"]),
                                                     transports=_transports(r["transports"]))
                       for r in existing]
            options = generate_registration_options(
                rp_id=settings.passkey_rp_id, rp_name=settings.passkey_rp_name,
                user_name=USER_NAME, user_id=_user_handle(conn),
                timeout=CHALLENGE_SECONDS * 1000,
                authenticator_selection=AuthenticatorSelectionCriteria(
                    resident_key=ResidentKeyRequirement.REQUIRED,
                    user_verification=UserVerificationRequirement.REQUIRED),
                exclude_credentials=exclude)
            _store_challenge(conn, options.challenge, KIND_REGISTER)
        return Response(options_to_json(options), media_type="application/json")

    @router.post("/register/verify", response_model=OkOut)
    def register_verify(body: RegisterVerifyIn) -> Response:
        """Burn the setup code, verify the attestation, store the passkey and unlock."""
        require_lock()
        with closing(connect(db_path)) as conn:
            if not _consume_setup_code(conn, body.setup_code):
                raise HTTPException(status_code=403, detail="invalid or expired setup code")
            try:
                cred = parse_registration_credential_json(body.credential)
                challenge = _consume_challenge(conn, cred.response.client_data_json,
                                               KIND_REGISTER)
                verified = _verify_registration(
                    credential=cred, expected_challenge=challenge,
                    expected_rp_id=settings.passkey_rp_id,
                    expected_origin=settings.passkey_origin, require_user_verification=True)
            except CEREMONY_ERRORS as exc:
                raise HTTPException(status_code=400, detail="registration failed") from exc
            transports = [t.value for t in cred.response.transports or []]
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO auth_credentials (credential_id, public_key, sign_count, "
                        "transports, created_at) VALUES (?, ?, ?, ?, ?)",
                        (bytes_to_base64url(verified.credential_id),
                         verified.credential_public_key, verified.sign_count,
                         json.dumps(transports), _iso(_now())))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(status_code=409, detail="passkey already registered") from exc
            return ok_with_session(conn)

    @router.post("/login/options")
    def login_options() -> Response:
        """PublicKeyCredentialRequestOptions for a discoverable passkey (empty allowCredentials)."""
        require_lock()
        options = generate_authentication_options(
            rp_id=settings.passkey_rp_id, timeout=CHALLENGE_SECONDS * 1000,
            user_verification=UserVerificationRequirement.REQUIRED)
        with closing(connect(db_path)) as conn:
            _store_challenge(conn, options.challenge, KIND_LOGIN)
        return Response(options_to_json(options), media_type="application/json")

    @router.post("/login/verify", response_model=OkOut)
    def login_verify(body: LoginVerifyIn) -> Response:
        """Verify the assertion against a stored passkey; 401 on any failure."""
        require_lock()
        with closing(connect(db_path)) as conn:
            try:
                cred = parse_authentication_credential_json(body.credential)
                challenge = _consume_challenge(conn, cred.response.client_data_json, KIND_LOGIN)
                cred_id = bytes_to_base64url(cred.raw_id)
                row = conn.execute("SELECT public_key, sign_count FROM auth_credentials "
                                   "WHERE credential_id=?", (cred_id,)).fetchone()
                if row is None:
                    raise LookupError("unknown credential")
                verified = _verify_authentication(
                    credential=cred, expected_challenge=challenge,
                    expected_rp_id=settings.passkey_rp_id,
                    expected_origin=settings.passkey_origin,
                    credential_public_key=bytes(row["public_key"]),
                    credential_current_sign_count=row["sign_count"],
                    require_user_verification=True)
            except CEREMONY_ERRORS as exc:
                raise HTTPException(status_code=401, detail="login failed") from exc
            with conn:
                conn.execute("UPDATE auth_credentials SET sign_count=?, last_used_at=? "
                             "WHERE credential_id=?",
                             (verified.new_sign_count, _iso(_now()), cred_id))
            return ok_with_session(conn)

    @router.post("/logout", status_code=204)
    def logout(request: Request) -> Response:
        """Delete this browser's session server-side and clear the cookie."""
        require_lock()
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            with closing(connect(db_path)) as conn, conn:
                conn.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_sha256(token),))
        resp = Response(status_code=204)
        resp.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict",
                           secure=settings.passkey_origin.startswith("https://"))
        return resp

    return router


def session_middleware(settings: Settings) -> Callable:
    """HTTP middleware: everything except /healthz and /api/auth/* needs a live session.

    Default-deny (stricter than "/api/* only"), so a future route can't be left open.
    """

    async def middleware(request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS or path.startswith(PUBLIC_PREFIX):
            return await call_next(request)
        token = request.cookies.get(SESSION_COOKIE)
        ok = await run_in_threadpool(check_session, settings.db_path, token,
                                     settings.auth_idle_minutes, True)
        if not ok:
            return JSONResponse(LOCKED, status_code=401)
        return await call_next(request)

    return middleware
