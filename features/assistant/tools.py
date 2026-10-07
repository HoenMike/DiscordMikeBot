from __future__ import annotations

import asyncio
import copy

import discord
from dataclasses import dataclass, field

from features.assistant.archive import archive_store
from features.assistant.providers.vectorize import archive_semantic
from features.assistant.router import RouteDecision


@dataclass(frozen=True)
class ToolExecutionResult:
    handled: bool
    command_text: str | None = None
    response_message_ids: tuple[int, ...] = ()
    response_context: str = ""
    details: dict = field(default_factory=dict)


def _render_bot_message(message, max_chars: int = 2200) -> str:
    parts: list[str] = []
    content = (getattr(message, "content", "") or "").strip()
    if content:
        parts.append(content)

    for embed in list(getattr(message, "embeds", None) or [])[:3]:
        title = (getattr(embed, "title", None) or "").strip()
        description = (getattr(embed, "description", None) or "").strip()
        if title:
            parts.append(title)
        if description:
            parts.append(description[:1200])
        for field in list(getattr(embed, "fields", None) or [])[:8]:
            name = (getattr(field, "name", None) or "").strip()
            value = (getattr(field, "value", None) or "").strip()
            if name or value:
                parts.append(f"{name}: {value}"[:700])

    for attachment in list(getattr(message, "attachments", None) or [])[:4]:
        filename = getattr(attachment, "filename", None)
        if filename:
            parts.append(f"[Attachment] {filename}")

    return "\n".join(parts)[:max_chars]


class CommandToolRegistry:
    """Closed bridge from typed assistant tools to existing prefix commands.

    A shallow copy of the Discord message is used so existing command parsing,
    checks and cooldowns run normally without mutating the live gateway event.
    """

    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    def _archive_snippet(item: dict) -> str:
        text = " ".join((item.get("source_content") or "").split())
        if not text:
            text = item.get("source_url") or "(không có text)"
        text = discord.utils.escape_mentions(text)
        return text[:180] + ("…" if len(text) > 180 else "")

    async def _execute_archive(
        self,
        decision: RouteDecision,
        message,
    ) -> ToolExecutionResult:
        owner_user_id = int(message.author.id)

        if decision.tool == "archive.save":
            item, error, created = await archive_store.save(
                owner_user_id,
                message,
                note=decision.arguments.get("note", ""),
            )
            if item is None:
                sent = await message.reply(
                    f"🧠 **Archive:** {error}",
                    mention_author=False,
                )
                return ToolExecutionResult(
                    handled=True,
                    response_message_ids=(int(sent.id),),
                    response_context=error,
                    details={
                        "archive_action": "save",
                        "archive_created": False,
                        "archive_status": "rejected",
                        "semantic_enabled": archive_semantic.enabled,
                    },
                )

            state = "Đã lưu" if created else "Mục này đã có trong Archive"
            snippet = self._archive_snippet(item)
            jump = item.get("source_jump_url") or item.get("source_url") or ""
            jump_text = f"\n🔗 [Jump to Message]({jump})" if jump else ""
            sent = await message.reply(
                f"✅ **{state} · #{item['id']}**\n"
                f"> {snippet}{jump_text}\n"
                f"*Chỉ bạn mới có thể tìm/xóa mục Archive này.*",
                mention_author=False,
            )
            if archive_semantic.enabled:
                asyncio.create_task(archive_semantic.upsert_item(item))
            return ToolExecutionResult(
                handled=True,
                response_message_ids=(int(sent.id),),
                response_context=f"Archive #{item['id']}: {snippet}",
                details={
                    "archive_action": "save",
                    "archive_id": int(item["id"]),
                    "archive_created": bool(created),
                    "archive_status": "saved" if created else "deduped",
                    "semantic_enabled": archive_semantic.enabled,
                    "semantic_index_queued": bool(archive_semantic.enabled),
                },
            )

        if decision.tool == "archive.search":
            query = decision.arguments.get("query", "")
            semantic_query = decision.arguments.get("semantic_query", "") or query
            lexical_items = await archive_store.search(
                owner_user_id,
                query=query,
                limit=5,
            )
            items = list(lexical_items)

            semantic_status = "disabled"
            semantic_ms = 0.0
            semantic_match_count = 0

            if query and archive_semantic.enabled:
                semantic_report = await archive_semantic.query_report(
                    owner_user_id,
                    semantic_query,
                    top_k=8,
                )
                matches = list(semantic_report.matches)
                semantic_status = semantic_report.status
                semantic_ms = semantic_report.elapsed_ms
                semantic_match_count = len(matches)
                if matches:
                    semantic_items = await archive_store.get_by_ids(
                        owner_user_id,
                        [match.archive_id for match in matches],
                    )
                    merged = []
                    seen_ids = set()
                    for item in [*semantic_items, *lexical_items]:
                        item_id = int(item["id"])
                        if item_id in seen_ids:
                            continue
                        seen_ids.add(item_id)
                        merged.append(item)
                        if len(merged) >= 5:
                            break
                    items = merged

                # Existing 3.3.0 rows may predate semantic indexing. Lazily index
                # the rows we already touched without delaying the response.
                for item in lexical_items:
                    asyncio.create_task(archive_semantic.upsert_item(item))

            if not items:
                sent = await message.reply(
                    "🔎 **Archive:** Mình chưa tìm thấy mục nào khớp.",
                    mention_author=False,
                )
                return ToolExecutionResult(
                    handled=True,
                    response_message_ids=(int(sent.id),),
                    response_context="Archive search returned no matches.",
                    details={
                        "archive_action": "search",
                        "archive_search_mode": (
                            "semantic_fallback"
                            if semantic_status in {"permission_error", "unavailable", "error"}
                            else (
                                "semantic_hybrid"
                                if semantic_status in {"ok", "no_match"}
                                else "lexical"
                            )
                        ),
                        "semantic_status": semantic_status,
                        "semantic_ms": round(semantic_ms, 1),
                        "semantic_matches": semantic_match_count,
                        "lexical_matches": len(lexical_items),
                        "result_count": 0,
                    },
                )

            lines = ["🧠 **ASUMI ARCHIVE**"]
            for item in items:
                snippet = self._archive_snippet(item)
                author = discord.utils.escape_mentions(
                    item.get("source_author_name") or "Unknown"
                )
                jump = item.get("source_jump_url") or item.get("source_url") or ""
                line = f"**#{item['id']}** · {author}\n> {snippet}"
                if jump:
                    line += f"\n[Jump to Message]({jump})"
                lines.append(line)

            sent = await message.reply(
                "\n\n".join(lines)[:1900],
                mention_author=False,
            )
            return ToolExecutionResult(
                handled=True,
                response_message_ids=(int(sent.id),),
                response_context="\n".join(
                    f"Archive #{item['id']}: {self._archive_snippet(item)}"
                    for item in items
                )[:6000],
                details={
                    "archive_action": "search",
                    "archive_search_mode": (
                        "semantic_fallback"
                        if semantic_status in {"permission_error", "unavailable", "error"}
                        else (
                            "semantic_hybrid"
                            if semantic_status in {"ok", "no_match"}
                            else "lexical"
                        )
                    ),
                    "semantic_status": semantic_status,
                    "semantic_ms": round(semantic_ms, 1),
                    "semantic_matches": semantic_match_count,
                    "lexical_matches": len(lexical_items),
                    "result_count": len(items),
                },
            )

        if decision.tool == "archive.forget":
            archive_id = int(decision.arguments.get("archive_id", 0) or 0)
            deleted = archive_id > 0 and await archive_store.forget(
                owner_user_id,
                archive_id,
            )
            if deleted and archive_semantic.enabled:
                asyncio.create_task(archive_semantic.delete_item(archive_id))
            text = (
                f"🗑️ Đã xóa **Archive #{archive_id}**."
                if deleted
                else f"Không tìm thấy **Archive #{archive_id}** thuộc về bạn."
            )
            sent = await message.reply(text, mention_author=False)
            return ToolExecutionResult(
                handled=True,
                response_message_ids=(int(sent.id),),
                response_context=text,
                details={
                    "archive_action": "forget",
                    "archive_id": archive_id,
                    "archive_deleted": bool(deleted),
                    "semantic_enabled": archive_semantic.enabled,
                    "semantic_delete_queued": bool(
                        deleted and archive_semantic.enabled
                    ),
                },
            )

        return ToolExecutionResult(handled=False)

    @staticmethod
    def _command_for(decision: RouteDecision) -> str | None:
        if decision.tool == "help.show":
            return ".m help"
        if decision.tool == "tarot.daily":
            return ".m tarot daily"
        if decision.tool == "tarot.launch":
            return ".m tarot"
        if decision.tool == "summary.catchup":
            hours = decision.arguments.get("hours")
            if hours is None:
                return ".m tomtat"
            safe_hours = max(0.1, min(float(hours), 168.0))
            return f".m tomtat {safe_hours:g}h"
        return None

    async def _capture_bot_outputs(self, message) -> tuple[tuple[int, ...], str]:
        channel = getattr(message, "channel", None)
        history = getattr(channel, "history", None)
        bot_user_id = getattr(getattr(self.bot, "user", None), "id", None)
        if history is None or bot_user_id is None:
            return (), ""

        captured = []
        try:
            async for item in history(
                limit=12,
                after=message,
                oldest_first=True,
            ):
                author_id = getattr(getattr(item, "author", None), "id", None)
                if author_id == bot_user_id:
                    captured.append(item)
        except Exception as exc:
            print(
                f"⚠️ [Asumi Tool] Không capture được output refs: "
                f"{type(exc).__name__}: {str(exc)[:120]}",
                flush=True,
            )
            return (), ""

        message_ids = tuple(
            int(item.id)
            for item in captured
            if getattr(item, "id", None) is not None
        )
        rendered = []
        remaining = 6000
        for item in captured:
            text = _render_bot_message(item)
            if not text:
                continue
            if len(text) > remaining:
                text = text[:remaining]
            rendered.append(text)
            remaining -= len(text)
            if remaining <= 0:
                break

        return message_ids[-8:], "\n\n".join(rendered)[:6000]

    async def execute(self, decision: RouteDecision, message) -> ToolExecutionResult:
        if decision.tool and decision.tool.startswith("archive."):
            try:
                return await self._execute_archive(decision, message)
            except Exception as exc:
                print(
                    f"❌ [Asumi Archive] {type(exc).__name__}: {str(exc)[:180]}",
                    flush=True,
                )
                sent = await message.reply(
                    "⚠️ Archive đang tạm thời không truy cập được. "
                    "Không có dữ liệu nào được lưu/xóa trong lần thử này.",
                    mention_author=False,
                )
                return ToolExecutionResult(
                    handled=True,
                    response_message_ids=(int(sent.id),),
                    response_context="Archive unavailable; no mutation confirmed.",
                    details={
                        "archive_status": "error",
                        "tool_error_type": type(exc).__name__,
                    },
                )

        command_text = self._command_for(decision)
        if not command_text:
            return ToolExecutionResult(handled=False)

        synthetic = copy.copy(message)
        synthetic.content = command_text
        await self.bot.process_commands(synthetic)

        response_ids, response_context = await self._capture_bot_outputs(message)
        return ToolExecutionResult(
            handled=True,
            command_text=command_text,
            response_message_ids=response_ids,
            response_context=response_context,
        )
