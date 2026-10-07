from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional


URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}


@dataclass(frozen=True)
class ImagePayload:
    data: bytes
    mime_type: str
    filename: str
    source_message_id: int | None = None
    source: str = "attachment"


@dataclass(frozen=True)
class ContextLine:
    author: str
    content: str
    message_id: int | None = None


@dataclass
class AssistantContext:
    reply: ContextLine | None = None
    recent: list[ContextLine] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    images: list[ImagePayload] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_recent_history: bool = False
    used_session_images: bool = False

    def to_prompt_text(self, max_chars: int = 7000) -> str:
        parts: list[str] = []

        if self.reply:
            parts.append(
                "Tin nhắn đang được reply:\n"
                f"{self.reply.author}: {self.reply.content or '(không có text)'}"
            )

        if self.recent:
            rendered = "\n".join(
                f"{line.author}: {line.content or '(không có text)'}"
                for line in self.recent
            )
            parts.append("Một số tin nhắn gần đây có liên quan:\n" + rendered)

        if self.urls:
            parts.append("URL được tham chiếu:\n" + "\n".join(self.urls[:8]))

        if self.images:
            names = ", ".join(img.filename for img in self.images)
            parts.append(
                f"Ảnh được gửi kèm làm context ({len(self.images)}): {names}. "
                "Hãy nhìn trực tiếp ảnh để trả lời, không đoán từ tên file."
            )

        if self.warnings:
            parts.append("Giới hạn context:\n" + "\n".join(self.warnings[:4]))

        text = "\n\n".join(parts)
        return text[:max_chars]


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def needs_recent_context(query: str) -> bool:
    folded = _fold(query)
    signals = (
        "nay gio",
        "vua roi",
        "hoi nay",
        "luc nay",
        "phia tren",
        "o tren",
        "tin nhan tren",
        "link tren",
        "link nay",
        "cai tren",
        "doan chat",
        "dang noi gi",
        "dang ban gi",
        "chuyen vua xay ra",
        "theo gui",
        "khai gui",
        "su ar gui",
        "moi nguoi",
        "tui no",
        "bon no",
    )
    return any(signal in folded for signal in signals)


def _extract_urls(text: str) -> list[str]:
    return [url.rstrip(".,!?)]}>") for url in URL_RE.findall(text or "")]


def _author_name(message) -> str:
    author = getattr(message, "author", None)
    return (
        getattr(author, "display_name", None)
        or getattr(author, "name", None)
        or "Unknown"
    )


def _line_from_message(message, max_chars: int = 1200) -> ContextLine:
    content = (getattr(message, "content", "") or "").strip()
    urls = _extract_urls(content)
    if not content and urls:
        content = " ".join(urls)
    return ContextLine(
        author=_author_name(message),
        content=content[:max_chars],
        message_id=getattr(message, "id", None),
    )


async def _resolve_reply_message(message):
    reference = getattr(message, "reference", None)
    if reference is None:
        return None

    resolved = getattr(reference, "resolved", None)
    if resolved is not None and hasattr(resolved, "content"):
        return resolved

    message_id = getattr(reference, "message_id", None)
    channel = getattr(message, "channel", None)
    fetch_message = getattr(channel, "fetch_message", None)
    if message_id and fetch_message:
        try:
            return await fetch_message(message_id)
        except Exception:
            return None
    return None


async def _read_images(
    messages: Iterable,
    *,
    max_images: int,
    max_image_bytes: int,
) -> tuple[list[ImagePayload], list[str]]:
    images: list[ImagePayload] = []
    warnings: list[str] = []
    seen: set[tuple[int | None, str]] = set()

    for msg in messages:
        if msg is None:
            continue
        for attachment in list(getattr(msg, "attachments", None) or []):
            if len(images) >= max_images:
                return images, warnings

            mime = (getattr(attachment, "content_type", None) or "").lower()
            filename = getattr(attachment, "filename", "image")
            key = (getattr(msg, "id", None), filename)
            if key in seen:
                continue
            seen.add(key)

            if mime not in SUPPORTED_IMAGE_TYPES:
                if mime.startswith("image/"):
                    warnings.append(
                        f"Bỏ qua ảnh {filename}: định dạng {mime or 'unknown'} chưa được hỗ trợ."
                    )
                continue

            size = int(getattr(attachment, "size", 0) or 0)
            if size and size > max_image_bytes:
                warnings.append(
                    f"Bỏ qua ảnh {filename}: {size} bytes vượt giới hạn {max_image_bytes} bytes."
                )
                continue

            read = getattr(attachment, "read", None)
            if not read:
                continue
            try:
                data = await read()
            except Exception:
                warnings.append(f"Không đọc được attachment {filename}.")
                continue

            if not data:
                continue
            if len(data) > max_image_bytes:
                warnings.append(
                    f"Bỏ qua ảnh {filename}: dữ liệu tải về vượt giới hạn."
                )
                continue

            images.append(
                ImagePayload(
                    data=data,
                    mime_type="image/jpeg" if mime == "image/jpg" else mime,
                    filename=filename,
                    source_message_id=getattr(msg, "id", None),
                    source="reply" if msg is not messages else "attachment",
                )
            )

    return images, warnings


class ContextBuilder:
    def __init__(
        self,
        *,
        recent_limit: int = 8,
        max_context_chars: int = 7000,
        max_images: int = 2,
        max_image_bytes: int = 5 * 1024 * 1024,
    ):
        self.recent_limit = max(1, min(int(recent_limit), 20))
        self.max_context_chars = max(1000, int(max_context_chars))
        self.max_images = max(1, min(int(max_images), 4))
        self.max_image_bytes = max(256 * 1024, int(max_image_bytes))

    @classmethod
    def from_env(cls) -> "ContextBuilder":
        return cls(
            recent_limit=int(os.getenv("ASUMI_CONTEXT_RECENT_MESSAGES", "8")),
            max_context_chars=int(os.getenv("ASUMI_CONTEXT_MAX_CHARS", "7000")),
            max_images=int(os.getenv("ASUMI_CONTEXT_MAX_IMAGES", "2")),
            max_image_bytes=int(
                os.getenv("ASUMI_CONTEXT_MAX_IMAGE_BYTES", str(5 * 1024 * 1024))
            ),
        )

    async def build(
        self,
        message,
        query: str,
        *,
        session=None,
        is_live_continuation: bool = False,
    ) -> AssistantContext:
        ctx = AssistantContext()
        reply_message = await _resolve_reply_message(message)

        # A reply to Asumi's own live-session answer is already represented by
        # session turns. Do not duplicate that bot response as explicit context.
        if reply_message is not None:
            is_session_bot_reply = (
                is_live_continuation
                and session is not None
                and getattr(reply_message, "id", None)
                == getattr(session, "last_response_message_id", None)
            )
            if not is_session_bot_reply:
                ctx.reply = _line_from_message(reply_message)
                ctx.urls.extend(_extract_urls(getattr(reply_message, "content", "") or ""))

        ctx.urls.extend(_extract_urls(getattr(message, "content", "") or ""))

        image_sources = [message]
        if reply_message is not None and not (
            is_live_continuation
            and session is not None
            and getattr(reply_message, "id", None)
            == getattr(session, "last_response_message_id", None)
        ):
            image_sources.append(reply_message)

        images, warnings = await _read_images(
            image_sources,
            max_images=self.max_images,
            max_image_bytes=self.max_image_bytes,
        )
        ctx.images.extend(images)
        ctx.warnings.extend(warnings)

        # Follow-up after an image answer inherits the bounded in-memory image
        # snapshot. A fresh explicit mention does not automatically drag old images.
        if (
            is_live_continuation
            and not ctx.images
            and session is not None
            and getattr(session, "images", None)
        ):
            ctx.images.extend(list(session.images)[: self.max_images])
            ctx.used_session_images = True

        if needs_recent_context(query):
            channel = getattr(message, "channel", None)
            history = getattr(channel, "history", None)
            if history:
                lines: list[ContextLine] = []
                try:
                    async for item in history(
                        limit=self.recent_limit,
                        before=message,
                        oldest_first=False,
                    ):
                        if getattr(item, "id", None) == getattr(reply_message, "id", None):
                            continue
                        # Skip system-like messages that have no author/content.
                        if getattr(item, "author", None) is None:
                            continue
                        lines.append(_line_from_message(item))
                except Exception:
                    lines = []

                lines.reverse()
                budget = self.max_context_chars
                selected: list[ContextLine] = []
                for line in reversed(lines):
                    cost = len(line.author) + len(line.content) + 4
                    if cost > budget and selected:
                        break
                    selected.append(line)
                    budget -= cost
                selected.reverse()
                ctx.recent = selected
                ctx.used_recent_history = bool(selected)
                for line in selected:
                    ctx.urls.extend(_extract_urls(line.content))

        # Preserve ordering while de-duplicating.
        ctx.urls = list(dict.fromkeys(ctx.urls))[:8]
        return ctx
