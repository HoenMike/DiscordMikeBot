import asyncio
from google import genai
import config

_ai_client = None


def get_ai_client() -> genai.Client:
    """Khởi tạo hoặc trả về client Google GenAI (sync + async dùng chung auth) cho các module AI."""
    global _ai_client
    if _ai_client is None:
        if config.GEMINI_API_KEY:
            _ai_client = genai.Client(api_key=config.GEMINI_API_KEY)
        else:
            raise ValueError("Chưa cấu hình GEMINI_API_KEY trong file .env!")
    return _ai_client


def get_aio_client() -> genai.client.AsyncClient:
    """Trả về AsyncClient của chính client dùng chung, cho phép await + hủy thật sự request nền."""
    return get_ai_client().aio


AI_CALL_SEMAPHORE = None


async def bounded_ai_generate(model: str, contents, config, timeout_sec: float, label: str = "AI"):
    """Gọi AI bất đồng bộ với timeout hủy được request nền và semaphore giới hạn đồng thời toàn cục."""
    global AI_CALL_SEMAPHORE
    if AI_CALL_SEMAPHORE is None:
        AI_CALL_SEMAPHORE = asyncio.Semaphore(6)
    client = get_aio_client()
    async with AI_CALL_SEMAPHORE:
        return await asyncio.wait_for(
            client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            ),
            timeout=timeout_sec,
        )


def split_text(text: str, limit: int | None = None) -> list[str]:
    """
    Chia nhỏ văn bản thành các phần không vượt quá `limit` ký tự.
    Ưu tiên ngắt tại các ranh giới tự nhiên (khối ngày `---`, dòng kẻ, đoạn văn `\\n\\n`)
    để tránh cắt ngang giữa một mốc timeline, thông điệp hoặc câu chuyện.
    """
    if limit is None:
        limit = config.DISCORD_EMBED_CHAR_LIMIT
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not text:
        return []

    chunks = []
    remaining = text.strip()
    while len(remaining) > limit:
        boundary = remaining.rfind('\n\n', 0, limit + 1)
        if boundary <= 0:
            boundary = remaining.rfind('\n', 0, limit + 1)
        if boundary <= 0:
            boundary = remaining.rfind(' ', 0, limit + 1)
        if boundary <= 0:
            boundary = limit
        chunk = remaining[:boundary].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[boundary:].lstrip('\n').strip()
    if remaining:
        chunks.append(remaining)
    return chunks
