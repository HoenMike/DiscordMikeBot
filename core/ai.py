import asyncio
import time
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


def _track_ai_call(model, label, outcome, elapsed_ms, response=None, error_type=None):
    """Telemetry must not change a successful AI request or expose content."""
    try:
        from core.ai_usage import usage_event, queue
        queue(usage_event(model=model, label=label, outcome=outcome,
                          response=response, latency_ms=elapsed_ms,
                          error_type=error_type))
    except Exception as exc:
        print("[AI Cost] tracking unavailable: " + type(exc).__name__, flush=True)


async def bounded_ai_generate(model: str, contents, config, timeout_sec: float, label: str = "AI"):
    """Bounded Gemini generation with non-blocking per-attempt usage telemetry."""
    global AI_CALL_SEMAPHORE
    if AI_CALL_SEMAPHORE is None:
        AI_CALL_SEMAPHORE = asyncio.Semaphore(6)
    started = time.perf_counter()
    try:
        client = get_aio_client()
        async with AI_CALL_SEMAPHORE:
            result = await asyncio.wait_for(
                client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_sec,
            )
    except asyncio.CancelledError:
        _track_ai_call(model, label, "cancelled",
                       int((time.perf_counter() - started) * 1000),
                       error_type="CancelledError")
        raise
    except Exception as exc:
        _track_ai_call(model, label, "failed",
                       int((time.perf_counter() - started) * 1000),
                       error_type=type(exc).__name__)
        raise
    _track_ai_call(model, label, "ok",
                   int((time.perf_counter() - started) * 1000),
                   response=result)
    return result

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
