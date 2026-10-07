from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.ai import split_text


@dataclass(frozen=True)
class ConversationDelivery:
    last_message: Any
    message_ids: tuple[int, ...]


async def send_conversation_reply(message, text: str) -> ConversationDelivery:
    chunks = split_text((text or "").strip(), limit=1900)
    if not chunks:
        chunks = ["Mình chưa tạo được câu trả lời cho tin nhắn này."]

    sent_messages = []
    sent = await message.reply(chunks[0], mention_author=False)
    sent_messages.append(sent)

    for chunk in chunks[1:]:
        sent = await message.channel.send(chunk)
        sent_messages.append(sent)

    return ConversationDelivery(
        last_message=sent,
        message_ids=tuple(
            int(item.id)
            for item in sent_messages
            if getattr(item, "id", None) is not None
        ),
    )
