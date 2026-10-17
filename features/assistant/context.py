from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Iterable, Optional


URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
USER_MENTION_RE = re.compile(r"<@!?(\d{1,20})>")
SUPPORTED_IMAGE_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}
IMAGE_EXTENSION_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
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
    requester: str | None = None
    mentioned_people: list[tuple[int, str]] = field(default_factory=list)
    social_referent: str | None = None
    social_referent_source: str | None = None
    prompt_char_limit: int = 7000
    history_minutes: int = 15
    recent: list[ContextLine] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    images: list[ImagePayload] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    used_recent_history: bool = False
    used_session_images: bool = False

    def to_prompt_text(self, max_chars: int | None = None) -> str:
        parts: list[str] = []

        if self.requester:
            parts.append(
                f"Người đang gọi Asumi (tác giả lời yêu cầu, KHÔNG phải "
                f"mục tiêu mặc định): {self.requester}"
            )
        if self.mentioned_people:
            parts.append(
                "Người được tag trong lời yêu cầu (Discord ID → tên thật "
                "trong server, không nhầm với người gọi):\n"
                + "\n".join(
                    f"<@{user_id}> = {name}"
                    for user_id, name in self.mentioned_people
                )
            )
        if self.social_referent:
            parts.append(
                f"Đối tượng được nhắc tới gần nhất: {self.social_referent} "
                f"(nguồn: {self.social_referent_source}). "
                "Đây là tham chiếu để hiểu câu, không tự suy diễn mọi lời "
                "nói đều nhằm công kích người này."
            )

        if self.reply:
            parts.append(
                "Tin nhắn gốc mà người gọi đang reply "
                f"(do {self.reply.author} gửi, không phải lời của người gọi):\n"
                f"{self.reply.author}: {self.reply.content or '(không có text)'}"
            )

        if self.recent:
            rendered = "\n".join(
                f"{line.author}: {line.content or '(không có text)'}"
                for line in self.recent
            )
            parts.append(
                f"Hội thoại trong cùng kênh, tối đa {self.history_minutes} phút trước, "
                "theo thứ tự cũ → mới (bao gồm cả bot khác, không mặc định "
                "mọi tin đều đang nói với Asumi):\n" + rendered
            )

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
        limit = self.prompt_char_limit if max_chars is None else max_chars
        return text[:max(1000, int(limit))]


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
        "cai nay",
        "cai truoc",
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


def needs_social_context(query: str) -> bool:
    """Short social references need a few nearby messages to resolve who's who.

    This only opts into bounded Discord channel context on an explicit Asumi
    mention/reply; it does not decide that a moderation request is a joke.
    """
    folded = _fold(query).replace("đ", "d")
    if len(folded) > 220:
        return False
    return bool(USER_MENTION_RE.search(query)) or bool(re.search(
        r"\b(?:thang|dua|ong|ba|nguoi|con|nho|cha)\s+(?:nay|kia|do)\b",
        folded,
    )) or any(cue in folded for cue in (
        "hua theo", "ca khia", "troll", "treu", "dua voi",
    ))


def needs_broad_recent_context(query: str) -> bool:
    folded = _fold(query)
    broad_signals = (
        "nay gio",
        "vua roi",
        "hoi nay",
        "luc nay",
        "doan chat",
        "dang noi gi",
        "dang ban gi",
        "chuyen vua xay ra",
        "moi nguoi",
        "tui no",
        "bon no",
    )
    return any(signal in folded for signal in broad_signals)


def _extract_urls(text: str) -> list[str]:
    return [url.rstrip(".,!?)]}>") for url in URL_RE.findall(text or "")]


def _mentioned_people(message, query: str) -> list[tuple[int, str]]:
    """Resolve ONLY actual user mentions supplied by Discord; bot mention was stripped.

    A display name written as plain text is not proof of a Discord mention.
    """
    ids = {int(value) for value in USER_MENTION_RE.findall(query)}
    requester_id = getattr(getattr(message, "author", None), "id", None)
    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    for member in getattr(message, "mentions", None) or []:
        user_id = getattr(member, "id", None)
        if user_id not in ids or user_id == requester_id or user_id in seen:
            continue
        name = _author_name_for_member(member)
        if name:
            result.append((user_id, name))
            seen.add(user_id)
        if len(result) >= 6:
            break
    return result


def _author_name_for_member(member) -> str:
    name = (
        getattr(member, "display_name", None)
        or getattr(member, "name", None)
        or ""
    )
    return str(name).replace("\n", " ").replace("\r", " ")[:80]


def _author_name(message) -> str:
    author = getattr(message, "author", None)
    return (
        getattr(author, "display_name", None)
        or getattr(author, "name", None)
        or "Unknown"
    )


def _line_from_message(message, max_chars: int = 1200) -> ContextLine:
    content = (getattr(message, "content", "") or "").strip()
    # Resolve mention IDs in nearby messages, not just the current request.
    # Without this, "@Regiko" and other bot names are opaque numeric IDs.
    for member in list(getattr(message, "mentions", None) or [])[:8]:
        member_id = getattr(member, "id", None)
        name = _author_name_for_member(member)
        if isinstance(member_id, int) and name:
            content = re.sub(
                rf"<@!?{member_id}>",
                lambda _match, label=name: f"@{label}",
                content,
            )
    # Message references already resolved by the gateway are cheap and clarify
    # which person/bot a participant was talking to. Never fetch N extra replies.
    reference = getattr(getattr(message, "reference", None), "resolved", None)
    if reference is not None and getattr(reference, "author", None) is not None:
        content = f"[reply to {_author_name(reference)}] {content}"
    extras: list[str] = []

    for embed in list(getattr(message, "embeds", None) or [])[:2]:
        title = (getattr(embed, "title", None) or "").strip()
        description = (getattr(embed, "description", None) or "").strip()
        url = (getattr(embed, "url", None) or "").strip()
        summary = " — ".join(part for part in (title, description[:500]) if part)
        if summary or url:
            extras.append(f"[Embed] {summary} {url}".strip())

    for attachment in list(getattr(message, "attachments", None) or [])[:4]:
        filename = getattr(attachment, "filename", None)
        content_type = getattr(attachment, "content_type", None)
        if filename:
            extras.append(
                f"[Attachment] {filename}"
                + (f" ({content_type})" if content_type else "")
            )

    if extras:
        content = "\n".join(part for part in [content, *extras] if part)

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

    for index, msg in enumerate(list(messages)):
        if msg is None:
            continue
        for attachment in list(getattr(msg, "attachments", None) or []):
            if len(images) >= max_images:
                return images, warnings

            mime = (getattr(attachment, "content_type", None) or "").lower()
            filename = getattr(attachment, "filename", "image")
            if not mime:
                lower_name = filename.lower()
                for extension, inferred_mime in IMAGE_EXTENSION_TYPES.items():
                    if lower_name.endswith(extension):
                        mime = inferred_mime
                        break
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
                    source="attachment" if index == 0 else "reply",
                )
            )

    return images, warnings


class ContextBuilder:
    def __init__(
        self,
        *,
        recent_limit: int = 40,
        lookback_minutes: int = 15,
        max_context_chars: int = 7000,
        max_images: int = 2,
        max_image_bytes: int = 5 * 1024 * 1024,
    ):
        self.recent_limit = max(1, min(int(recent_limit), 60))
        self.lookback_minutes = max(1, min(int(lookback_minutes), 30))
        self.max_context_chars = max(1000, int(max_context_chars))
        self.max_images = max(1, min(int(max_images), 4))
        self.max_image_bytes = max(256 * 1024, int(max_image_bytes))

    @classmethod
    def from_env(cls) -> "ContextBuilder":
        from core import constants as policy
        return cls(
            recent_limit=policy.ASUMI_CONTEXT_RECENT_MESSAGES,
            lookback_minutes=policy.ASUMI_CONTEXT_LOOKBACK_MINUTES,
            max_context_chars=policy.ASUMI_CONTEXT_MAX_CHARS,
            max_images=policy.ASUMI_CONTEXT_MAX_IMAGES,
            max_image_bytes=policy.ASUMI_CONTEXT_MAX_IMAGE_BYTES,
        )

    async def build(
        self,
        message,
        query: str,
        *,
        session=None,
        is_live_continuation: bool = False,
    ) -> AssistantContext:
        ctx = AssistantContext(
            prompt_char_limit=self.max_context_chars,
            history_minutes=self.lookback_minutes,
            requester=_author_name(message),
        )
        ctx.mentioned_people = _mentioned_people(message, query)
        reply_message = await _resolve_reply_message(message)

        # Plain chat replies are already represented by bounded session turns.
        # Tool outputs are different: Tarot/Summary messages can be edited or
        # enriched after command execution, so read the replied bot message live.
        session_response_ids = []
        if session is not None:
            session_response_ids = list(
                getattr(session, "response_message_ids", None)
                or [getattr(session, "last_response_message_id", None)]
            )
        is_session_bot_reply = (
            is_live_continuation
            and session is not None
            and getattr(reply_message, "id", None) in session_response_ids
        )
        should_read_live_tool_output = bool(
            is_session_bot_reply and getattr(session, "last_tool", None)
        )

        if reply_message is not None and (
            not is_session_bot_reply or should_read_live_tool_output
        ):
            ctx.reply = _line_from_message(reply_message)
            ctx.urls.extend(_extract_urls(ctx.reply.content))

        # A single explicit non-bot mention outranks a replied-to bystander.
        # Multiple mentions are ambiguous; do not silently select a target.
        if len(ctx.mentioned_people) == 1:
            ctx.social_referent = ctx.mentioned_people[0][1]
            ctx.social_referent_source = "mention trong lời yêu cầu"
        elif not ctx.mentioned_people and ctx.reply:
            ctx.social_referent = ctx.reply.author
            ctx.social_referent_source = "tác giả tin được reply"

        ctx.urls.extend(_extract_urls(getattr(message, "content", "") or ""))

        image_sources = [message]
        if reply_message is not None and (
            not is_session_bot_reply or should_read_live_tool_output
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

        # A two-word invitation such as "chơi ko?" must see the conversation
        # that preceded it, even though it has no lexical "context" keywords.
        # Only explicitly invoked Asumi requests reach this builder. Read the
        # *same channel* on demand, without persisting anyone's chat history.
        if query.strip():
            channel = getattr(message, "channel", None)
            history = getattr(channel, "history", None)
            if history:
                anchor = getattr(message, "created_at", None) or datetime.now(timezone.utc)
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                cutoff = anchor - timedelta(minutes=self.lookback_minutes)
                lines: list[ContextLine] = []
                try:
                    # Discord returns newest first. after= enforces the 15m
                    # server-side window; local timestamps guard test/mock APIs.
                    async for item in history(
                        limit=self.recent_limit,
                        after=cutoff,
                        before=message,
                        oldest_first=False,
                    ):
                        if len(lines) >= self.recent_limit:
                            break
                        if getattr(item, "id", None) == getattr(reply_message, "id", None):
                            continue
                        if getattr(item, "author", None) is None:
                            continue
                        item_at = getattr(item, "created_at", None)
                        if item_at is not None:
                            if item_at.tzinfo is None:
                                item_at = item_at.replace(tzinfo=timezone.utc)
                            if not (cutoff <= item_at < anchor):
                                continue
                        lines.append(_line_from_message(item, max_chars=600))
                except Exception:
                    lines = []

                # Keep most recent utterances, but reserve space for reply,
                # participant metadata, URLs and the current user request.
                budget = max(600, self.max_context_chars - 1700)
                selected: list[ContextLine] = []
                for line in lines:
                    cost = len(line.author) + len(line.content) + 4
                    if cost > budget:
                        if not selected:
                            line = ContextLine(
                                author=line.author,
                                content=line.content[:max(0, budget - len(line.author) - 4)],
                                message_id=line.message_id,
                            )
                            selected.append(line)
                        break
                    selected.append(line)
                    budget -= cost
                ctx.recent = list(reversed(selected))
                ctx.used_recent_history = bool(selected)
                for line in ctx.recent:
                    ctx.urls.extend(_extract_urls(line.content))

        # Preserve ordering while de-duplicating.
        ctx.urls = list(dict.fromkeys(ctx.urls))[:8]
        return ctx
