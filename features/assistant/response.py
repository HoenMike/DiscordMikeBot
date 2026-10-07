from __future__ import annotations

from core.ai import split_text


async def send_conversation_reply(message, text: str):
    chunks = split_text((text or "").strip(), limit=1900)
    if not chunks:
        chunks = ["Mình chưa tạo được câu trả lời cho tin nhắn này."]

    sent = await message.reply(chunks[0], mention_author=False)
    for chunk in chunks[1:]:
        sent = await message.channel.send(chunk)
    return sent
