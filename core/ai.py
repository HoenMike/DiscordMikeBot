from google import genai
import config

_ai_client = None

def get_ai_client() -> genai.Client:
    """Khởi tạo hoặc trả về client Google GenAI dùng chung cho các module AI."""
    global _ai_client
    if _ai_client is None:
        if config.GEMINI_API_KEY:
            _ai_client = genai.Client(api_key=config.GEMINI_API_KEY)
        else:
            raise ValueError("Chưa cấu hình GEMINI_API_KEY trong file .env!")
    return _ai_client


def split_text(text: str, limit: int | None = None) -> list[str]:
    """
    Chia nhỏ văn bản thành các phần không vượt quá `limit` ký tự.
    Ưu tiên ngắt tại các ranh giới tự nhiên (khối ngày `---`, dòng kẻ, đoạn văn `\\n\\n`)
    để tránh cắt ngang giữa một mốc timeline, thông điệp hoặc câu chuyện.
    """
    if limit is None:
        limit = config.DISCORD_EMBED_CHAR_LIMIT
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para)
        # Nếu một đoạn vượt quá giới hạn, phân chia nhỏ hơn theo từng dòng
        if para_len > limit:
            lines = para.split('\n')
            for line in lines:
                line_len = len(line)
                if current_length + line_len + 1 > limit:
                    if current_chunk:
                        chunks.append('\n\n'.join(current_chunk).strip())
                        current_chunk = []
                        current_length = 0
                if line_len > limit:
                    # Cắt thô nếu 1 dòng đơn lẻ vượt quá limit
                    chunks.append(line[:limit])
                    line = line[limit:]
                current_chunk.append(line)
                current_length += len(line) + 1
        else:
            if current_length + para_len + 2 > limit:
                if current_chunk:
                    chunks.append('\n\n'.join(current_chunk).strip())
                    current_chunk = []
                    current_length = 0
            current_chunk.append(para)
            current_length += para_len + 2

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk).strip())

    return [c for c in chunks if c.strip()]
