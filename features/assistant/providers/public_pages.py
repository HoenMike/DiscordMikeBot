"""Bounded public source-page excerpts for factual Brave Search answers.

This is NOT an arbitrary URL fetch tool. Only HTTPS Brave-result URLs whose
hostname matches the reviewed source allowlist are read; redirects are not
followed, response bytes are limited, and no Discord/private context is passed.
"""
from __future__ import annotations

import asyncio
import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlsplit

import aiohttp

from core import constants as policy

ALLOWED_HOSTS = (
    "wikipedia.org", "vnexpress.net", "vietnamnet.vn", "tuoitre.vn",
    "thanhnien.vn", "nhandan.vn", "baochinhphu.vn",
    "petrolimex.com.vn", "pvoil.com.vn", "moit.gov.vn",
    "congthuong.vn", "open-meteo.com",
)


def safe_public_url(url: str) -> bool:
    parts = urlsplit(str(url or ""))
    host = (parts.hostname or "").lower().rstrip(".")
    if parts.scheme != "https" or parts.port not in (None, 443):
        return False
    if parts.username or parts.password or not host:
        return False
    if re.search(r"[\\\x00-\x1f\x7f]", url) or len(url) > 550:
        return False
    return any(host == d or host.endswith("." + d) for d in ALLOWED_HOSTS)


class _PublicText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg", "nav", "footer", "noscript"}:
            self.skip_stack.append(tag)

    def handle_endtag(self, tag):
        if self.skip_stack and tag == self.skip_stack[-1]:
            self.skip_stack.pop()

    def handle_data(self, data):
        if not self.skip_stack and data.strip():
            self.parts.append(data.strip())


def relevant_page_excerpt(document: str, query: str, limit: int = 1600) -> str:
    parser = _PublicText()
    try:
        parser.feed(document)
    except Exception:
        return ""
    clean = " ".join(html.unescape(" ".join(parser.parts)).split())
    if not clean:
        return ""
    # Anchor near words actually in the question to avoid generic site
    # navigation dominating a short factual answer.
    words = [
        word.lower() for word in re.findall(r"[\wÀ-ỹ]{4,}", query)
        if word.lower() not in {"hôm", "nay", "như", "nào", "trên", "tìm", "giúp"}
    ][:8]
    low = clean.lower()
    positions = [low.find(w) for w in words if low.find(w) >= 0]
    start = max(0, min(positions) - 170) if positions else 0
    return clean[start:start + limit]


@dataclass(frozen=True)
class PublicPageEvidence:
    url: str
    text: str


async def fetch_public_page_evidence(query: str, hits) -> tuple[PublicPageEvidence, ...]:
    """Read at most two pre-approved domains; fail open to Brave snippets."""
    candidates = [h for h in hits if safe_public_url(h.url)][:policy.ASUMI_PUBLIC_PAGE_MAX_SOURCES]
    if not policy.ASUMI_PUBLIC_PAGE_READING_ENABLED or not candidates:
        return ()
    timeout = aiohttp.ClientTimeout(total=policy.ASUMI_PUBLIC_PAGE_TIMEOUT_SECONDS)

    async def one(session, hit):
        try:
            async with session.get(
                hit.url,
                allow_redirects=False,
                headers={"Accept": "text/html", "User-Agent": "AsumiBot/3.7 PublicFactReader"},
            ) as response:
                if response.status != 200:
                    return None
                if "text/html" not in response.headers.get("Content-Type", ""):
                    return None
                body = await response.content.read(policy.ASUMI_PUBLIC_PAGE_MAX_BYTES + 1)
                if len(body) > policy.ASUMI_PUBLIC_PAGE_MAX_BYTES:
                    return None
                excerpt = relevant_page_excerpt(body.decode("utf-8", "replace"), query)
                if len(excerpt) < 100:
                    return None
                return PublicPageEvidence(url=hit.url, text=excerpt)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeError):
            return None

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            result = await asyncio.gather(*(one(session, hit) for hit in candidates))
        return tuple(x for x in result if x is not None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return ()
