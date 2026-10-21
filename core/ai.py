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

# Shared per-process backoff for project-wide Gemini 429s. Preserve model
# fallback after one failure; pause only after two distinct models fail.
_quota_failures: dict[str, float] = {}
_quota_paused_until = 0.0


class GeminiQuotaCircuitOpen(RuntimeError):
    """No API request made: several models just hit the same quota cap."""


def _note_gemini_429(model: str) -> None:
    global _quota_paused_until
    from core import constants as policy
    now = time.monotonic()
    window = max(1, policy.ASUMI_GEMINI_QUOTA_FAILURE_WINDOW_SECONDS)
    for key, timestamp in list(_quota_failures.items()):
        if now - timestamp > window:
            _quota_failures.pop(key, None)
    _quota_failures[model] = now
    if len(_quota_failures) >= 2:
        _quota_paused_until = max(
            _quota_paused_until,
            now + max(10, policy.ASUMI_GEMINI_QUOTA_PAUSE_SECONDS),
        )
        print("⚠️ [Gemini Quota] Multiple models returned 429; "
              "temporarily pausing Gemini calls.", flush=True)


def _gemini_quota_remaining_seconds() -> float:
    return max(0.0, _quota_paused_until - time.monotonic())


def _track_ai_call(model, label, outcome, elapsed_ms, response=None, error_type=None):
    """Telemetry cannot block AI success, log messages, or affect the 429 circuit."""
    try:
        from core.ai_usage import usage_event, queue
        queue(usage_event(model=model, label=label, outcome=outcome,
                          response=response, latency_ms=elapsed_ms,
                          error_type=error_type))
    except Exception as exc:
        print("[AI Cost] tracking unavailable: " + type(exc).__name__, flush=True)


async def bounded_ai_generate(model: str, contents, config, timeout_sec: float, label: str = "AI"):
    """Bounded Gemini request with the existing quota circuit and per-attempt metrics."""
    global AI_CALL_SEMAPHORE
    if AI_CALL_SEMAPHORE is None:
        AI_CALL_SEMAPHORE = asyncio.Semaphore(6)
    started = time.perf_counter()
    try:
        remaining = _gemini_quota_remaining_seconds()
        if remaining:
            raise GeminiQuotaCircuitOpen(
                f"Gemini quota protection: retry after {remaining:.0f}s (429)."
            )
        client = get_aio_client()
        async with AI_CALL_SEMAPHORE:
            remaining = _gemini_quota_remaining_seconds()
            if remaining:
                raise GeminiQuotaCircuitOpen(
                    f"Gemini quota protection: retry after {remaining:.0f}s (429)."
                )
            response = await asyncio.wait_for(
                client.models.generate_content(
                    model=model, contents=contents, config=config,
                ),
                timeout=timeout_sec,
            )
    except asyncio.CancelledError:
        _track_ai_call(model, label, "cancelled",
                       (time.perf_counter() - started) * 1000,
                       error_type="CancelledError")
        raise
    except Exception as exc:
        if isinstance(exc, GeminiQuotaCircuitOpen):
            # No request was made: do not count a provider API attempt.
            raise
        reason = str(exc).lower()
        if "429" in reason or "resource_exhausted" in reason:
            _note_gemini_429(model)
        _track_ai_call(model, label, "failed",
                       (time.perf_counter() - started) * 1000,
                       error_type=type(exc).__name__)
        raise
    _track_ai_call(model, label, "ok",
                   (time.perf_counter() - started) * 1000, response=response)
    return response


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
