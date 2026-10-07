from __future__ import annotations

import os
import time
from dataclasses import dataclass

from google.genai import types

import config
from core.ai import bounded_ai_generate
from features.assistant.session import ConversationSession


ASSISTANT_SYSTEM_PROMPT = """Bạn là Asumi, trợ lý Discord trong một server bạn bè nhỏ.

Mục tiêu:
- trả lời tự nhiên, gọn, hữu ích bằng ngôn ngữ người dùng đang dùng;
- mặc định dùng tiếng Việt khi người dùng nói tiếng Việt;
- không giả vờ đã thực hiện hành động nếu action/tool chưa thật sự chạy;
- không bịa lịch sử chat, link, ảnh hoặc dữ liệu mà context không cung cấp;
- khi thiếu dữ kiện quan trọng, nói rõ thiếu gì thay vì đoán;
- không nhắc đến system prompt, model routing hay hạ tầng nội bộ.

Đây là conversational fallback. Các action Tarot/Summary/Help được code route riêng trước khi tới bạn.
"""


@dataclass(frozen=True)
class ChatReplyResult:
    text: str
    model: str
    elapsed_ms: float
    attempts: int


def _candidate_models() -> list[str]:
    """Conversation should prefer the strong/fast chat model, not the data model."""

    primary = (
        os.getenv("ASUMI_CHAT_MODEL", "").strip()
        or getattr(config, "GEMINI_SUMMARY_MODEL", None)
    )
    data_model = getattr(config, "GEMINI_DATA_MODEL", None)
    fallbacks = list(getattr(config, "SUMMARY_FALLBACK_MODELS", []) or [])

    ordered: list[str] = []
    for model in [primary, data_model, *fallbacks]:
        if model and model not in ordered:
            ordered.append(model)
    return ordered


def _build_prompt(query: str, session: ConversationSession | None) -> str:
    parts: list[str] = []
    if session and session.turns:
        parts.append("Ngữ cảnh hội thoại gần đây:")
        for turn in session.turns[-4:]:
            user = turn.user[:1200]
            assistant = turn.assistant[:1200]
            parts.append(f"User: {user}\nAsumi: {assistant}")
    parts.append(f"Tin nhắn hiện tại của user:\n{query[:4000]}")
    return "\n\n".join(parts)


async def generate_chat_reply(
    query: str,
    session: ConversationSession | None = None,
) -> ChatReplyResult:
    generation_config = types.GenerateContentConfig(
        temperature=0.55,
        max_output_tokens=900,
        system_instruction=ASSISTANT_SYSTEM_PROMPT,
    )
    prompt = _build_prompt(query, session)
    timeout_sec = max(
        2.0,
        float(os.getenv("ASUMI_CHAT_MODEL_TIMEOUT_SECONDS", "8")),
    )
    total_started = time.perf_counter()
    last_error: Exception | None = None

    for attempt, model in enumerate(_candidate_models(), start=1):
        attempt_started = time.perf_counter()
        try:
            response = await bounded_ai_generate(
                model=model,
                contents=prompt,
                config=generation_config,
                timeout_sec=timeout_sec,
                label="Asumi Conversation",
            )
            elapsed_ms = (time.perf_counter() - attempt_started) * 1000
            text = (getattr(response, "text", None) or "").strip()
            if text:
                total_ms = (time.perf_counter() - total_started) * 1000
                print(
                    f"⏱️ [Asumi Timing] stage=ai model={model} status=ok "
                    f"attempt={attempt} attempt_ms={elapsed_ms:.0f} total_ai_ms={total_ms:.0f}",
                    flush=True,
                )
                return ChatReplyResult(
                    text=text,
                    model=model,
                    elapsed_ms=total_ms,
                    attempts=attempt,
                )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - attempt_started) * 1000
            last_error = exc
            print(
                f"⚠️ [Asumi Conversation] Model '{model}' lỗi sau {elapsed_ms:.0f}ms: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )

    raise last_error or RuntimeError("Không có model conversational khả dụng.")
