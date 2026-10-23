"""OAuth account connections with encrypted tokens and honest persistence status.

This module deliberately never accepts passwords, payment card numbers, CVVs,
or browser cookies. Platform adapters can request an access token server-side
after a provider has been connected with OAuth.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import time
import base64
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet, InvalidToken


def _now() -> int:
    return int(time.time())


def _fernet() -> Fernet:
    key = os.getenv("NEXUS_CONNECTION_ENCRYPTION_KEY", "").strip().encode()
    if not key:
        raise RuntimeError("Connection encryption key is not configured")
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Connection encryption key is invalid") from exc


def _provider_configs() -> Dict[str, Dict[str, Any]]:
    raw = os.getenv("NEXUS_OAUTH_PROVIDERS", "{}").strip() or "{}"
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OAuth provider configuration is invalid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("OAuth provider configuration must be an object")
    return {str(key).casefold(): item for key, item in value.items() if isinstance(item, dict)}


def _https_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("https://")


def _render_storage_is_durable(db_path: str) -> bool:
    """Local files are durable in development; Render needs its mounted disk."""
    if not os.getenv("RENDER") and not os.getenv("RENDER_SERVICE_ID"):
        return True
    mount = Path("/var/data")
    try:
        resolved = Path(db_path).expanduser().resolve()
        return mount.is_mount() and resolved.is_relative_to(mount.resolve())
    except (OSError, RuntimeError, ValueError):
        return False


class ConnectionManager:
    """Track OAuth state and encrypt provider tokens in the operational DB."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        if db_path != ":memory:" and not db_path.startswith("file:"):
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False,
                               uri=self.db_path.startswith("file:"))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_connections (
                    provider_id TEXT PRIMARY KEY,
                    provider_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    remember_me INTEGER NOT NULL DEFAULT 0,
                    token_ciphertext BLOB,
                    expires_at INTEGER,
                    connected_at TEXT,
                    checked_at TEXT,
                    error_code TEXT,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nexus_oauth_states (
                    state_hash TEXT PRIMARY KEY,
                    provider_id TEXT NOT NULL,
                    verifier_ciphertext BLOB NOT NULL,
                    remember_me INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nexus_oauth_expiry ON nexus_oauth_states(expires_at)")

    def _config(self, provider_id: str) -> Dict[str, Any]:
        provider_id = provider_id.casefold()
        config = _provider_configs().get(provider_id)
        if not config:
            raise KeyError("OAuth provider is not configured")
        if not _https_url(config.get("authorize_url")) or not _https_url(config.get("token_url")):
            raise ValueError("Provider authorization and token endpoints must use HTTPS")
        client_id_env = config.get("client_id_env")
        if not isinstance(client_id_env, str) or not os.getenv(client_id_env):
            raise ValueError("Provider client ID is not configured")
        secret_env = config.get("client_secret_env")
        if secret_env and not os.getenv(str(secret_env)):
            raise ValueError("Provider client secret is not configured")
        redirect_uri = os.getenv("NEXUS_OAUTH_REDIRECT_URI", "").strip()
        if not _https_url(redirect_uri):
            raise ValueError("NEXUS_OAUTH_REDIRECT_URI must be configured with HTTPS")
        return config

    def _durable(self) -> bool:
        return _render_storage_is_durable(self.db_path)

    def _encryption_ready(self) -> bool:
        try:
            _fernet()
            return True
        except RuntimeError:
            return False

    def list_connections(self) -> Dict[str, Any]:
        configs = _provider_configs()
        with self._connect() as conn:
            rows = {
                row["provider_id"]: dict(row)
                for row in conn.execute("SELECT * FROM nexus_connections").fetchall()
            }
        providers = []
        for provider_id, config in configs.items():
            row = rows.get(provider_id, {})
            supports_refresh = bool(config.get("supports_refresh"))
            providers.append({
                "provider_id": provider_id,
                "name": str(config.get("name") or provider_id),
                "status": row.get("status", "NOT_CONNECTED"),
                "configured": self._provider_ready(provider_id, config),
                "remember_me": bool(row.get("remember_me", False)),
                "remember_me_available": (
                    supports_refresh and self._durable() and self._encryption_ready()
                ),
                "scopes": json.loads(row.get("scopes_json", "[]")),
                "connected_at": row.get("connected_at"),
                "checked_at": row.get("checked_at"),
                "error_code": row.get("error_code"),
                "supports_refresh": supports_refresh,
            })
        return {
            "providers": providers,
            "storage": {
                "encryption_ready": self._encryption_ready(),
                "durable": self._durable(),
                "remember_me_ready": self._durable() and self._encryption_ready(),
                "reason": None if self._durable() and self._encryption_ready() else (
                    "encryption_key_missing" if not self._encryption_ready()
                    else "durable_storage_missing"
                ),
            },
        }

    @staticmethod
    def _provider_ready(provider_id: str, config: Dict[str, Any]) -> bool:
        client_id_env = config.get("client_id_env")
        secret_env = config.get("client_secret_env")
        return bool(
            _https_url(config.get("authorize_url"))
            and _https_url(config.get("token_url"))
            and isinstance(client_id_env, str)
            and os.getenv(client_id_env)
            and (not secret_env or os.getenv(str(secret_env)))
            and _https_url(os.getenv("NEXUS_OAUTH_REDIRECT_URI", ""))
            and os.getenv("NEXUS_CONNECTION_ENCRYPTION_KEY")
        )

    def start_oauth(self, provider_id: str, remember_me: bool) -> Dict[str, Any]:
        provider_id = provider_id.casefold()
        config = self._config(provider_id)
        if not self._encryption_ready():
            raise ValueError("Connection encryption is not configured")
        if remember_me and not (config.get("supports_refresh") and self._durable()):
            raise ValueError("Durable storage and provider refresh-token support are required for Remember me")

        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        fernet = _fernet()
        expires_at = _now() + 600
        with self._connect() as conn:
            conn.execute("DELETE FROM nexus_oauth_states WHERE expires_at < ?", (_now(),))
            conn.execute(
                "INSERT INTO nexus_oauth_states(state_hash,provider_id,verifier_ciphertext,remember_me,expires_at) "
                "VALUES(?,?,?,?,?)",
                (hashlib.sha256(state.encode()).hexdigest(), provider_id,
                 fernet.encrypt(verifier.encode()), int(remember_me), expires_at),
            )
        params: Dict[str, str] = {
            "client_id": os.environ[str(config["client_id_env"])],
            "redirect_uri": os.environ["NEXUS_OAUTH_REDIRECT_URI"],
            "response_type": "code",
            "scope": " ".join(str(scope) for scope in config.get("scopes", [])),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if remember_me:
            params.update({str(key): str(value) for key, value in (config.get("offline_params") or {}).items()})
        return {"authorization_url": f"{config['authorize_url']}?{urlencode(params)}"}

    def complete_oauth(self, code: str, state: str) -> Dict[str, Any]:
        if not code or not state or len(code) > 4096 or len(state) > 256:
            raise ValueError("Invalid OAuth callback")
        state_hash = hashlib.sha256(state.encode()).hexdigest()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM nexus_oauth_states WHERE state_hash=?", (state_hash,)
            ).fetchone()
            if row is None or row["expires_at"] < _now():
                raise ValueError("OAuth state is missing or expired")
            conn.execute("DELETE FROM nexus_oauth_states WHERE state_hash=?", (state_hash,))
        provider_id = row["provider_id"]
        config = self._config(provider_id)
        verifier = _fernet().decrypt(row["verifier_ciphertext"]).decode()
        token_data = self._exchange_code(config, code, verifier)
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Provider did not return an access token")
        remember_requested = bool(row["remember_me"])
        refresh_token = token_data.get("refresh_token")
        # OAuth providers may ignore offline access or omit refresh tokens.
        # Never claim a durable remembered session when renewal is impossible.
        remember_me = remember_requested and isinstance(refresh_token, str) and bool(refresh_token)
        tokens = {
            "access_token": access_token,
            "token_type": token_data.get("token_type", "Bearer"),
            "refresh_token": refresh_token if remember_me else None,
        }
        expires_in = token_data.get("expires_in")
        expires_at = _now() + int(expires_in) if str(expires_in or "").isdigit() else None
        scopes = token_data.get("scope") or config.get("scopes", [])
        if isinstance(scopes, str):
            scopes = scopes.split()
        if not isinstance(scopes, list):
            scopes = []
        encrypted = _fernet().encrypt(json.dumps(tokens, separators=(",", ":")).encode())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO nexus_connections(provider_id,provider_name,status,scopes_json,remember_me,"
                "token_ciphertext,expires_at,connected_at,checked_at,error_code,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,strftime('%Y-%m-%dT%H:%M:%fZ','now')) "
                "ON CONFLICT(provider_id) DO UPDATE SET provider_name=excluded.provider_name,"
                "status=excluded.status,scopes_json=excluded.scopes_json,remember_me=excluded.remember_me,"
                "token_ciphertext=excluded.token_ciphertext,expires_at=excluded.expires_at,"
                "connected_at=excluded.connected_at,checked_at=excluded.checked_at,error_code=NULL,"
                "updated_at=excluded.updated_at",
                (provider_id, str(config.get("name") or provider_id), "AUTHORIZED",
                 json.dumps(scopes), int(remember_me), encrypted, expires_at,
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), None),
            )
        return {"provider_id": provider_id, "status": "AUTHORIZED", "remember_me": remember_me}

    def _exchange_code(self, config: Dict[str, Any], code: str, verifier: str) -> Dict[str, Any]:
        client_id = os.environ[str(config["client_id_env"])]
        secret_env = config.get("client_secret_env")
        client_secret = os.getenv(str(secret_env), "") if secret_env else ""
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": os.environ["NEXUS_OAUTH_REDIRECT_URI"],
            "client_id": client_id,
            "code_verifier": verifier,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        if client_secret and config.get("client_auth_method", "client_secret_basic") == "client_secret_basic":
            import base64
            credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {credentials}"
            form.pop("client_id")
        elif client_secret:
            form["client_secret"] = client_secret
        request = Request(str(config["token_url"]), data=urlencode(form).encode(), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ValueError("OAuth provider token exchange failed") from exc
        if not isinstance(result, dict):
            raise ValueError("OAuth provider returned an invalid token response")
        return result

    def disconnect(self, provider_id: str) -> Dict[str, str]:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE nexus_connections SET status='DISCONNECTED',token_ciphertext=NULL,"
                "remember_me=0,error_code=NULL,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE provider_id=?", (provider_id.casefold(),)
            )
        if cursor.rowcount == 0:
            raise KeyError("Connection not found")
        return {"provider_id": provider_id.casefold(), "status": "DISCONNECTED"}

    def get_access_token(self, provider_id: str) -> str:
        """Return a usable token to a provider adapter without exposing it to the UI."""
        provider_id = provider_id.casefold()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM nexus_connections WHERE provider_id=? AND status='AUTHORIZED'",
                (provider_id,),
            ).fetchone()
        if row is None or row["token_ciphertext"] is None:
            raise KeyError("Connection is not authorized")
        try:
            tokens = json.loads(_fernet().decrypt(row["token_ciphertext"]).decode())
        except (InvalidToken, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("Stored credentials cannot be decrypted") from exc
        if row["expires_at"] and row["expires_at"] < _now() + 60:
            refresh_token = tokens.get("refresh_token")
            if not refresh_token or not row["remember_me"]:
                raise RuntimeError("Connection expired; reconnect required")
            refreshed = self._refresh(provider_id, refresh_token)
            tokens["access_token"] = refreshed["access_token"]
            tokens["refresh_token"] = refreshed.get("refresh_token", refresh_token)
            expires_in = refreshed.get("expires_in")
            expires_at = _now() + int(expires_in) if str(expires_in or "").isdigit() else None
            encrypted = _fernet().encrypt(json.dumps(tokens, separators=(",", ":")).encode())
            with self._connect() as conn:
                conn.execute(
                    "UPDATE nexus_connections SET token_ciphertext=?,expires_at=?,"
                    "checked_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),error_code=NULL "
                    "WHERE provider_id=?", (encrypted, expires_at, provider_id)
                )
        return str(tokens["access_token"])

    def _refresh(self, provider_id: str, refresh_token: str) -> Dict[str, Any]:
        config = self._config(provider_id)
        client_id = os.environ[str(config["client_id_env"])]
        secret_env = config.get("client_secret_env")
        client_secret = os.getenv(str(secret_env), "") if secret_env else ""
        form = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
        headers = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        if client_secret and config.get("client_auth_method", "client_secret_basic") == "client_secret_basic":
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            form.pop("client_id")
        elif client_secret:
            form["client_secret"] = client_secret
        request = Request(str(config["token_url"]), data=urlencode(form).encode(), headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE nexus_connections SET status='RECONNECT_REQUIRED',error_code='TOKEN_REFRESH_FAILED' "
                    "WHERE provider_id=?", (provider_id,)
                )
            raise RuntimeError("Provider token refresh failed; reconnect required") from exc
        if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
            raise RuntimeError("Provider token refresh returned an invalid response")
        return result
