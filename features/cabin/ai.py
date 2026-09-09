"""
features/cabin/ai.py - Tích hợp gọi Gemini AI cho tính năng Dịch Cabin trực tiếp.
"""

import asyncio
import re
from typing import List, Tuple
from google.genai import types
import config
from core.ai import get_ai_client
from features.cabin.constants import (
    CABIN_FALLBACK_MODELS,
    DEFAULT_CABIN_MODEL,
)

# Giới hạn tối đa 3 request dịch cabin đồng thời để tránh chạm hạn mức rate-limit
CABIN_SEMAPHORE = asyncio.Semaphore(3)

CABIN_SYSTEM_PROMPT = """Bạn là một 'Phiên dịch viên Cabin' (Simultaneous Interpreter) siêu bựa, cực kỳ sắc sảo và hài hước trên một máy chủ Discord.

NGUYÊN TẮC CỐT LÕI (BẮT BUỘC TUÂN THỦ 100%):
1. TẬP TRUNG TUYỆT ĐỐI VÀO CÂU NÓI CỦA NẠN NHÂN (VICTIM-CENTRIC):
   - Trọng tâm 100% là bóc mẽ, bẻ lái, châm biếm đúng nội dung câu nạn nhân vừa phát ngôn.
   - Nạn nhân nói về điều gì (ví dụ: khẳng định giới tính 'im not gay', than đói, khoe đồ, phân trần, chém gió, bao biện...), bot dịch sâu cay, hài hước thẳng vào câu nói đó!
   - Bối cảnh lịch sử chat (nếu có) CHỈ LÀ THAM KHẢO PHỤ để biết không khí trò chuyện hoặc người đối thoại. TUYỆT ĐỐI KHÔNG lấy chủ đề cũ của người khác làm biến dạng hoặc lạc đề khỏi câu nói của nạn nhân!

2. BẮT BUỘC NÓI Ở GÓC NHÌN NGÔI THỨ NHẤT (First-person: "Tao", "Tôi", "Mình", "Em"):
   - Đóng vai chính nạn nhân tự thú nhận sự thật thầm kín, lươn lẹo, sĩ diện hão, chối quanh hoặc tâm can thật sự đằng sau câu nói.
   - Ví dụ:
     + Nạn nhân nói: "im not gay 🐱" -> "Mồm tao bảo không gay nhưng tay gài vội icon con mèo cute để gạ tình, đừng có soi nữa!"
     + Nạn nhân nói: "tối nay bận làm việc rồi" -> "Tao sợ vào game feed mạng bị chửi nên bịa cớ làm deadline để giữ chút thể diện."
   - TUYỆT ĐỐI TRÁNH ngôi thứ hai hoặc thứ ba: Không bao giờ dùng "Hắn ta...", "Nó đang...", "Bạn này muốn nói là...", "Ý của hắn là...".

3. DỨT KHOÁT & HOÀN CHỈNH:
   - Trả về TRỰC TIẾP nội dung câu dịch (chỉ từ 1 đến 2 câu ngắn gọn, đắt giá, súc tích, kết thúc câu hoàn chỉnh).
   - TUYỆT ĐỐI KHÔNG bỏ lửng câu (không kết thúc lửng lơ như 'nên phải...', 'để...', 'thì...').
   - TUYỆT ĐỐI KHÔNG chèn tiền tố như "Dịch cabin:", "🎙️", "Ý tao là:", "Nói cách khác là:"...
   - Ngôn ngữ tự nhiên, dí dỏm, phong cách văn hóa mạng / Gen Z Việt Nam.
"""

CABIN_CONFIG = types.GenerateContentConfig(
    temperature=0.85,
    max_output_tokens=1200,
    system_instruction=CABIN_SYSTEM_PROMPT,
)


def _clean_cabin_output(text: str) -> str:
    """Loại bỏ các tiền tố hoặc định dạng thừa nếu AI lỡ sinh ra."""
    if not text:
        return ""

    cleaned = text.strip()
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    # 1. Xóa emoji microphone hoặc tai nghe ở đầu
    cleaned = re.sub(r"^[\s🎙️🎧*]+", "", cleaned)
    # 2. Xóa các khối ngoặc vuông tiền tố như [Cabin], [Dịch cabin], [Dịch cabin - Bóc mẽ], v.v.
    cleaned = re.sub(r"^\[.*?\]\s*[:：\-]?\s*", "", cleaned)
    # 3. Xóa các cụm từ mở đầu dạng tiền tố giải thích
    cleaned = re.sub(
        r"^(?:dịch\s*cabin|cabin|phiên\s*dịch|ý\s*của\s*(?:hắn|người\s*này|tao|tôi)\s*là|ý\s*(?:hắn|tao|tôi)\s*là|nói\s*cách\s*khác\s*là|nói\s*thẳng\s*ra\s*là)\s*[:：\-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE
    )
    cleaned = cleaned.strip()

    # Lặp lại lượt 2 đề phòng trường hợp lồng nhau (ví dụ: 🎙️ [Cabin]: Ý là...)
    cleaned = re.sub(r"^[\s🎙️🎧*]+", "", cleaned)
    cleaned = re.sub(r"^(?:ý\s*là)\s*[:：\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Loại bỏ lại ngoặc kép nếu xuất hiện sau khi cắt tiền tố
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    return cleaned


def is_incomplete_sentence(text: str) -> bool:
    """Kiểm tra xem câu dịch có bị cắt ngang hoặc kết thúc dang dở không."""
    if not text or len(text.strip()) < 4:
        return True

    cleaned = text.strip()

    # Các từ nối / giới từ / từ dang dở nếu nằm ở cuối câu thì chứng tỏ bị ngắt lời
    dangling_endings = {
        "nên phải", "phải", "để", "và", "nhưng", "thì", "vì", "rồi",
        "là", "bị", "được", "hoặc", "nếu", "mà", "cũng", "do", "tại", "sẽ", "đang"
    }

    words = cleaned.split()
    if words:
        last_word = re.sub(r"[^\w\s]", "", words[-1]).lower()
        last_two = (
            re.sub(r"[^\w\s]", "", f"{words[-2]} {words[-1]}").lower()
            if len(words) >= 2 else ""
        )
        if last_two in dangling_endings or last_word in dangling_endings:
            return True

    return False


async def generate_cabin_interpretation(
    target_name: str,
    target_message: str,
    context_messages: List[Tuple[str, str]],
) -> str:
    """
    Sinh bản dịch cabin troll hài hước dựa trên tin nhắn của target (ngữ cảnh chat chỉ làm phụ).
    
    :param target_name: Tên hiển thị của người bị cabin
    :param target_message: Tin nhắn nạn nhân vừa gửi
    :param context_messages: Danh sách các tin nhắn gần đây [(author_name, content), ...]
    :return: Câu phiên dịch cabin ngắn gọn, hài hước ở góc nhìn ngôi thứ nhất
    """
    # Xây dựng đoạn bối cảnh phụ (chỉ lấy tối đa 3-4 tin nhắn gần nhất)
    context_str = ""
    if context_messages:
        recent_ctx = context_messages[-4:]
        lines = [f"- {author}: {content}" for author, content in recent_ctx]
        context_str = "(Bối cảnh vài câu trò chuyện gần nhất trong kênh chỉ dùng để tham khảo phụ:\n" + "\n".join(lines) + ")\n\n"

    user_prompt = (
        f"🎯 TIN NHẮN CỦA NẠN NHÂN [{target_name}] CẦN PHIÊN DỊCH CABIN:\n"
        f"\"{target_message}\"\n\n"
        f"{context_str}"
        f"👉 Hãy phiên dịch cabin CÂU NÓI TRÊN CỦA [{target_name}] sang ngôi thứ nhất (nói thay {target_name}, tự thú nhận sự thật bựa/sĩ diện/lươn lẹo đằng sau đúng câu này, xưng 'Tao' hoặc 'Tôi/Mình', ngắn gọn 1-2 câu hoàn chỉnh, TUYỆT ĐỐI KHÔNG bỏ lửng câu):"
    )

    async with CABIN_SEMAPHORE:
        last_error = None
        for model_name in CABIN_FALLBACK_MODELS:
            try:
                client = get_ai_client()
                # Giới hạn tối đa 7 giây mỗi lần gọi AI để phản hồi siêu tốc
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=user_prompt,
                        config=CABIN_CONFIG,
                    ),
                    timeout=7.0
                )

                # Kiểm tra nếu bị cắt ngang do chạm max_output_tokens
                cand = response.candidates[0] if (response and response.candidates) else None
                if cand and getattr(cand, "finish_reason", None) == types.FinishReason.MAX_TOKENS:
                    print(f"⚠️ [Cabin AI] Model '{model_name}' bị cắt ngang (MAX_TOKENS), thử fallback...", flush=True)
                    continue

                raw_text = response.text or ""
                cleaned = _clean_cabin_output(raw_text)

                # Kiểm tra nếu câu bị cụt hoặc dang dở
                if is_incomplete_sentence(cleaned):
                    print(f"⚠️ [Cabin AI] Model '{model_name}' sinh câu chưa hoàn chỉnh ('{cleaned[:40]}...'), thử fallback...", flush=True)
                    continue

                if cleaned:
                    print(f"✅ [Cabin AI] Model '{model_name}' đã tạo bản dịch cabin thành công!", flush=True)
                    return cleaned
            except asyncio.TimeoutError:
                print(f"⏱️ [Cabin AI] Model '{model_name}' quá thời gian 7s, chuyển sang model dự phòng...", flush=True)
                last_error = "Timeout 7s"
            except Exception as e:
                print(f"⚠️ [Cabin AI] Model '{model_name}' gặp lỗi: {e}, thử fallback...", flush=True)
                last_error = e

        # Nếu tất cả các model đều gặp lỗi, trả về fallback hài hước
        print(f"❌ [Cabin AI] Toàn bộ model Gemini đều thất bại: {last_error}", flush=True)
        return "Tai nghe của phiên dịch viên vừa nổ do câu nói quá ảo diệu, không thể phiên dịch nổi!"
