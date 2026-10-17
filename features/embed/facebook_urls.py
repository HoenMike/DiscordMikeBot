"""Resolve public Facebook short Reel/video share URLs without cookies or third-party redirects.

This is best effort. Never promise access to private/auth-gated videos, and never
follow a redirect beyond the allow-listed Facebook HTTPS hosts.
"""
import asyncio
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp

_ALLOWED_HOSTS = frozenset({
    "facebook.com", "www.facebook.com", "m.facebook.com",
    "web.facebook.com", "mbasic.facebook.com",
})
_SHORT_VIDEO = re.compile(r"^/share/[rv]/[A-Za-z0-9_-]+/?$")
_DIRECT_REEL = re.compile(r"^/reels?/(\\d+)/?$")
_DIRECT_VIDEO = re.compile(r"/videos/(\\d+)(?:/|$)")
_MAX_REDIRECTS = 4
_HTML_LIMIT = 98304
_RESOLVE_TIMEOUT = aiohttp.ClientTimeout(total=5.0, connect=2.0)


def _trusted_facebook_url(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and (parsed.hostname or "").lower() in _ALLOWED_HOSTS
            and parsed.username is None and parsed.password is None
            and (parsed.port is None or parsed.port == 443)
        )
    except ValueError:
        return False


def _direct_video_url(url: str) -> str | None:
    """Accept only a public-looking, exact Facebook video route (not /login)."""
    if not _trusted_facebook_url(url):
        return None
    parsed = urlsplit(url)
    reel = _DIRECT_REEL.fullmatch(parsed.path)
    if reel:
        return f"https://www.facebook.com/reel/{reel.group(1)}/"
    video = _DIRECT_VIDEO.search(parsed.path)
    if video:
        return f"https://www.facebook.com/watch/?v={video.group(1)}"
    if parsed.path.rstrip("/") == "/watch":
        value = parse_qs(parsed.query).get("v", [""])[0]
        if value.isdecimal() and len(value) <= 32:
            return f"https://www.facebook.com/watch/?v={value}"
    return None


class _VideoCanonicalParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "meta" and attributes.get("property", "").casefold() in {"og:url", "al:web:url"}:
            self.urls.append(attributes.get("content", ""))
        if tag == "link" and attributes.get("rel", "").casefold() == "canonical":
            self.urls.append(attributes.get("href", ""))


async def resolve_facebook_share_video(session: aiohttp.ClientSession, original_url: str) -> str | None:
    """Return a numeric /reel/ or /watch/ URL only when publicly discoverable.

    No cookies, no Facebook credentials, no proxy-to-arbitrary-host requests,
    bounded time and redirects; None preserves the original embed pipeline.
    """
    if not _trusted_facebook_url(original_url) or not _SHORT_VIDEO.fullmatch(urlsplit(original_url).path):
        return None

    current = original_url
    try:
        async with asyncio.timeout(5.5):
            for _ in range(_MAX_REDIRECTS + 1):
                if not _trusted_facebook_url(current):
                    return None
                direct = _direct_video_url(current)
                if direct:
                    return direct

                async with session.get(
                    current, timeout=_RESOLVE_TIMEOUT, allow_redirects=False,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "Accept": "text/html,application/xhtml+xml",
                    },
                ) as response:
                    if response.status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location", "")
                        if not location:
                            return None
                        candidate = urljoin(current, location)
                        if not _trusted_facebook_url(candidate):
                            return None
                        current = candidate
                        continue
                    if response.status != 200:
                        return None
                    content_type = response.headers.get("Content-Type", "").lower()
                    if "text/html" not in content_type:
                        return None
                    parser = _VideoCanonicalParser()
                    parser.feed((await response.content.read(_HTML_LIMIT)).decode("utf-8", errors="ignore"))
                    for canonical in parser.urls:
                        resolved = _direct_video_url(urljoin(current, canonical))
                        if resolved:
                            return resolved
                    return None
    except (TimeoutError, asyncio.TimeoutError, aiohttp.ClientError, UnicodeError, ValueError):
        return None
    return None
