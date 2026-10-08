"""Owner-only OAuth 2.1 authorization-code + PKCE for Asumi private MCP.

No static Render API key is ever sent to ChatGPT. A logged-in dashboard
administrator consents interactively. All codes and bearer tokens are stored
hashed in Turso, bounded by lifetime, resource, client and scope.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass

from core.db import db_client

ISSUER = "https://discordmikebot.onrender.com"
RESOURCE = ISSUER + "/api/feedback-connector/mcp"
SCOPE = "feedback:read feedback:propose"
CHALLENGE_METADATA = ISSUER + "/.well-known/oauth-protected-resource"
REDIRECT_PATTERN = re.compile(r"^https://chatgpt\.com/connector/oauth/[a-zA-Z0-9_-]{8,160}$")
LEGACY_REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"
PKCE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
CODE_TTL = 300
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 86400


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status: int = 400):
        super().__init__(description)
        self.error = error
        self.description = description
        self.status = status


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")


def valid_redirect(uri: str) -> bool:
    return bool(REDIRECT_PATTERN.fullmatch(uri) or uri == LEGACY_REDIRECT)


def _credentials() -> str:
    return secrets.token_urlsafe(48)


async def _query(sql: str, args: tuple = ()) -> list[tuple]:
    await db_client.connect()
    if not db_client.is_cloud:
        raise OAuthError("temporarily_unavailable", "Turso Cloud unavailable", 503)
    async with db_client.execute(sql, args) as cur:
        rows = await cur.fetchall()
    if not db_client.is_cloud:
        raise OAuthError("temporarily_unavailable", "Turso Cloud unavailable", 503)
    return rows


async def _change(sql: str, args: tuple) -> int:
    await db_client.connect()
    if not db_client.is_cloud:
        raise OAuthError("temporarily_unavailable", "Turso Cloud unavailable", 503)
    async with db_client.execute(sql, args) as cur:
        changed = cur.rowcount
    if not db_client.is_cloud:
        raise OAuthError("temporarily_unavailable", "Turso Cloud unavailable", 503)
    return changed


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS asumi_oauth_clients (
      client_id TEXT PRIMARY KEY,
      redirect_uri TEXT NOT NULL,
      created_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS asumi_oauth_codes (
      code_hash TEXT PRIMARY KEY,
      client_id TEXT NOT NULL,
      redirect_uri TEXT NOT NULL,
      challenge TEXT NOT NULL,
      resource TEXT NOT NULL,
      scope TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      consumed INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS asumi_oauth_tokens (
      token_hash TEXT PRIMARY KEY,
      client_id TEXT NOT NULL,
      resource TEXT NOT NULL,
      scope TEXT NOT NULL,
      token_type TEXT NOT NULL,
      expires_at INTEGER NOT NULL,
      revoked INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE INDEX IF NOT EXISTS asumi_oauth_tokens_expiry
        ON asumi_oauth_tokens (expires_at)""",
)


async def init_oauth_tables() -> None:
    for query in SCHEMA:
        await _change(query, ())


async def register_chatgpt_client(redirect_uris: object) -> dict:
    if (
        not isinstance(redirect_uris, list)
        or len(redirect_uris) != 1
        or not isinstance(redirect_uris[0], str)
        or not valid_redirect(redirect_uris[0])
    ):
        raise OAuthError("invalid_redirect_uri", "Only official ChatGPT callback URLs are accepted")
    client_id = "chatgpt-" + _credentials()
    await _change(
        "INSERT INTO asumi_oauth_clients(client_id,redirect_uri,created_at) VALUES(?,?,?)",
        (client_id, redirect_uris[0], int(time.time())),
    )
    return {
        "client_id": client_id,
        "client_id_issued_at": int(time.time()),
        "client_name": "ChatGPT — Asumi Feedback",
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }


async def validate_auth_request(params: dict) -> dict:
    client_id = str(params.get("client_id", ""))
    redirect_uri = str(params.get("redirect_uri", ""))
    challenge = str(params.get("code_challenge", ""))
    resource = str(params.get("resource", ""))
    scope = str(params.get("scope", ""))
    response_type = str(params.get("response_type", ""))
    state = str(params.get("state", ""))
    if not 8 <= len(state) <= 512 or not re.fullmatch(r"[\x21-\x7e]+", state):
        raise OAuthError("invalid_request", "OAuth state is required")
    if response_type != "code" or params.get("code_challenge_method") != "S256":
        raise OAuthError("unsupported_response_type", "Authorization code with PKCE S256 is required")
    if not PKCE_PATTERN.fullmatch(challenge):
        raise OAuthError("invalid_request", "Invalid PKCE challenge")
    requested = scope.split()
    if resource != RESOURCE or set(requested) != set(SCOPE.split()) or len(requested) != len(SCOPE.split()):
        raise OAuthError("invalid_scope", "Resource or requested scope is not allowed")
    matches = await _query(
        "SELECT redirect_uri FROM asumi_oauth_clients WHERE client_id=?",
        (client_id,),
    )
    if not matches or not valid_redirect(redirect_uri) or redirect_uri != matches[0][0]:
        raise OAuthError("invalid_client", "Unknown OAuth client or redirect URI")
    return {
        "client_id": client_id, "redirect_uri": redirect_uri,
        "challenge": challenge, "scope": SCOPE,
        "resource": resource, "state": state,
    }


async def issue_code(pending: dict) -> str:
    code = _credentials()
    await _change(
        "INSERT INTO asumi_oauth_codes(code_hash,client_id,redirect_uri,challenge,resource,scope,expires_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            _digest(code), pending["client_id"], pending["redirect_uri"],
            pending["challenge"], pending["resource"], pending["scope"],
            int(time.time()) + CODE_TTL,
        ),
    )
    return code


async def _issue_pair(client_id: str, resource: str, scope: str) -> dict:
    access, refresh = _credentials(), _credentials()
    now = int(time.time())
    await _change(
        "INSERT INTO asumi_oauth_tokens"
        "(token_hash,client_id,resource,scope,token_type,expires_at) VALUES(?,?,?,?,?,?)",
        (_digest(access), client_id, resource, scope, "access", now + ACCESS_TTL),
    )
    await _change(
        "INSERT INTO asumi_oauth_tokens"
        "(token_hash,client_id,resource,scope,token_type,expires_at) VALUES(?,?,?,?,?,?)",
        (_digest(refresh), client_id, resource, scope, "refresh", now + REFRESH_TTL),
    )
    return {
        "access_token": access, "token_type": "Bearer",
        "expires_in": ACCESS_TTL, "scope": scope, "refresh_token": refresh,
    }


async def exchange_code(params: dict) -> dict:
    client_id = str(params.get("client_id", ""))
    code = str(params.get("code", ""))
    redirect_uri = str(params.get("redirect_uri", ""))
    resource = str(params.get("resource", ""))
    verifier = str(params.get("code_verifier", ""))
    if not PKCE_PATTERN.fullmatch(verifier) or resource != RESOURCE:
        raise OAuthError("invalid_grant", "Invalid PKCE or resource")
    rows = await _query(
        "SELECT client_id,redirect_uri,challenge,resource,scope,expires_at,consumed "
        "FROM asumi_oauth_codes WHERE code_hash=?",
        (_digest(code),),
    )
    if not rows:
        raise OAuthError("invalid_grant", "Invalid authorization code")
    saved_client, saved_redirect, challenge, saved_resource, scope, expires_at, consumed = rows[0]
    if (
        saved_client != client_id or saved_redirect != redirect_uri
        or saved_resource != resource or consumed or expires_at < int(time.time())
        or not hmac.compare_digest(_pkce_challenge(verifier), challenge)
    ):
        raise OAuthError("invalid_grant", "Authorization code expired, consumed, or PKCE mismatch")
    changed = await _change(
        "UPDATE asumi_oauth_codes SET consumed=1 WHERE code_hash=? AND consumed=0 AND expires_at>=?",
        (_digest(code), int(time.time())),
    )
    if changed != 1:
        raise OAuthError("invalid_grant", "Authorization code already consumed")
    return await _issue_pair(client_id, resource, scope)


async def refresh_access_token(params: dict) -> dict:
    refresh = str(params.get("refresh_token", ""))
    client_id = str(params.get("client_id", ""))
    resource = str(params.get("resource", ""))
    if not refresh or resource != RESOURCE:
        raise OAuthError("invalid_grant", "Invalid refresh token or resource")
    rows = await _query(
        "SELECT client_id,resource,scope,expires_at,revoked FROM asumi_oauth_tokens "
        "WHERE token_hash=? AND token_type='refresh'",
        (_digest(refresh),),
    )
    if not rows:
        raise OAuthError("invalid_grant", "Unknown refresh token")
    saved_client, saved_resource, scope, expires_at, revoked = rows[0]
    if saved_client != client_id or saved_resource != resource or revoked or expires_at < int(time.time()):
        raise OAuthError("invalid_grant", "Expired or revoked refresh token")
    changed = await _change(
        "UPDATE asumi_oauth_tokens SET revoked=1 WHERE token_hash=? "
        "AND revoked=0 AND expires_at>=?",
        (_digest(refresh), int(time.time())),
    )
    if changed != 1:
        raise OAuthError("invalid_grant", "Refresh token already used")
    return await _issue_pair(client_id, resource, scope)


async def authorize_bearer(value: str) -> bool:
    if not value.startswith("Bearer "):
        return False
    token = value[7:].strip()
    if len(token) < 32 or len(token) > 256:
        return False
    rows = await _query(
        "SELECT resource,scope,expires_at,revoked FROM asumi_oauth_tokens "
        "WHERE token_hash=? AND token_type='access'",
        (_digest(token),),
    )
    if not rows:
        return False
    resource, scope, expiry, revoked = rows[0]
    return resource == RESOURCE and scope == SCOPE and expiry > int(time.time()) and not revoked

async def revoke_all_owner_tokens() -> int:
    """Explicit admin revocation of every outstanding ChatGPT MCP token."""
    await db_client.connect()
    if not db_client.is_cloud:
        raise OAuthError("temporarily_unavailable", "Turso Cloud unavailable", 503)
    changed = await _change(
        "UPDATE asumi_oauth_tokens SET revoked=1 WHERE revoked=0",
        (),
    )
    return changed
