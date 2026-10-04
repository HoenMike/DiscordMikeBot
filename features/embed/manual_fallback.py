"""Signed, short-lived manual fallback links for social previews."""

from __future__ import annotations

from typing import Any

from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer

import config

_FALLBACK_SALT = "asumi-facebook-manual-fallback-v1"
_FALLBACK_MAX_AGE_SECONDS = 15 * 60


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.FLASK_SECRET_KEY, salt=_FALLBACK_SALT)


def build_manual_fallback_url(
    *,
    origin_message_id: int,
    channel_id: int,
    author_id: int,
    platform_key: str,
    original_url: str,
    is_spoiler: bool = False,
) -> str | None:
    """Build a signed one-click fallback URL when the public web base is available."""
    base_url = getattr(config, "PUBLIC_BASE_URL", "")
    if not base_url:
        return None

    payload = {
        "v": 1,
        "origin_id": int(origin_message_id),
        "channel_id": int(channel_id),
        "author_id": int(author_id),
        "platform": str(platform_key),
        "url": str(original_url),
        "is_spoiler": bool(is_spoiler),
    }
    token = _serializer().dumps(payload)
    return f"{base_url.rstrip('/')}/embed/fallback/{token}"


def verify_manual_fallback_token(
    token: str,
    *,
    max_age: int = _FALLBACK_MAX_AGE_SECONDS,
) -> dict[str, Any] | None:
    """Validate a signed fallback token and return its payload, or None if invalid/expired."""
    try:
        payload = _serializer().loads(token, max_age=max_age)
    except (BadData, SignatureExpired):
        return None

    if not isinstance(payload, dict) or payload.get("v") != 1:
        return None

    required = ("origin_id", "channel_id", "author_id", "platform", "url")
    if any(key not in payload for key in required):
        return None

    try:
        payload["origin_id"] = int(payload["origin_id"])
        payload["channel_id"] = int(payload["channel_id"])
        payload["author_id"] = int(payload["author_id"])
    except (TypeError, ValueError):
        return None

    if payload["platform"] != "facebook":
        return None
    if not str(payload["url"]).startswith(("http://", "https://")):
        return None

    payload["is_spoiler"] = bool(payload.get("is_spoiler", False))
    return payload
