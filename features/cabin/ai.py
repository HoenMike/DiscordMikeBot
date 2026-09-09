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

BẢN CHẤT CỦA DỊCH CABIN:
Người phiên dịch cabin PHẢI NÓI THAY LỜI DIỄN GIẢ Ở GÓC NHÌN NGÔI THỨ NHẤT (First-person perspective: "Tao", "Tôi", "Mình", "Em").

Nhiệm vụ của bạn:
1. Đọc bối cảnh đoạn chat gần đây (nếu có) để hiểu mọi người đang bàn về chủ đề gì (chơi game, than ế, đi ăn, công việc, drama, code, v.v.).
2. Khi người mục tiêu vừa nhắn một câu, hãy 'phiên dịch cabin' câu nói đó sang tầng ý nghĩa thật sự thầm kín nhất, NHƯNG BẮT BUỘC PHẢI NÓI Ở GÓC NHÌN NGÔI THỨ NHẤT ("Tao", "Tôi", "Mình", "Em" tùy độ thân mật của ngữ cảnh). Như thể chính người đó đang tự thú nhận nỗi lòng xấu hổ, sự lươn lẹo hoặc thói tự luyến của bản thân!

QUY TẮC CỐT LÕI (BẮT BUỘC TUÂN THỦ):
- BẮT BUỘC DÙNG NGÔI THỨ NHẤT ("Tao", "Tôi", "Mình", "Em"):
  + ĐÚNG (Nói thay người đó): "Tao sợ vào game feed mạng bị chúng mày chửi nên bịa cớ làm deadline để giữ chút thể diện."
  + ĐÚNG (Tự thú): "Thực ra tao nhịn ăn 3 tháng để đú cái điện thoại này, mau khen tao giàu đi!"
  + TUYỆT ĐỐI TRÁNH NGÔI THỨ HAI HOẶC THỨ BA: Không bao giờ dùng "Hắn ta...", "Nó đang...", "Bạn này muốn nói là...", "Ý của hắn là...".
- Trả về TRỰC TIẾP nội dung câu dịch (chỉ từ 1 đến 2 câu ngắn gọn, đắt giá, súc tích).
- TUYỆT ĐỐI KHÔNG chèn thêm tiền tố như "Dịch cabin:", "🎙️", "Ý tao là:", "Nói cách khác là:"... Hệ thống sẽ tự động ghép tiền tố hiển thị.
- Tận dụng tối đa ngữ cảnh gần đây để tự thú / bẻ nghĩa khớp với cuộc trò chuyện.
- Ngôn ngữ tự nhiên, dí dỏm, phong cách văn hóa mạng / Gen Z Việt Nam, mang tính tự vạch áo cho người xem lưng cực hài hước.
"""

CABIN_CONFIG = types.GenerateContentConfig(
    temperature=0.85,
    max_output_tokens=350,
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


async def generate_cabin_interpretation(
    target_name: str,
    target_message: str,
    context_messages: List[Tuple[str, str]],
) -> str:
    """
    Sinh bản dịch cabin troll hài hước dựa trên bối cảnh cuộc trò chuyện và tin nhắn của target.
    
    :param target_name: Tên hiển thị của người bị cabin
    :param target_message: Tin nhắn nạn nhân vừa gửi
    :param context_messages: Danh sách các tin nhắn gần đây [(author_name, content), ...]
    :return: Câu phiên dịch cabin ngắn gọn, hài hước ở góc nhìn ngôi thứ nhất
    """
    # Xây dựng đoạn bối cảnh
    context_str = ""
    if context_messages:
        lines = []
        for author, content in context_messages:
            lines.append(f"- {author}: {content}")
        context_str = "Bối cảnh các tin nhắn gần đây trong kênh:\n" + "\n".join(lines) + "\n\n"
    else:
        context_str = "Kênh vừa mới bắt đầu hoặc chưa có nhiều tin nhắn trò chuyện trước đó.\n\n"

    user_prompt = (
        f"{context_str}"
        f"Người mục tiêu [{target_name}] vừa gửi tin nhắn sau:\n"
        f"\"{target_message}\"\n\n"
        f"Hãy phiên dịch cabin câu nói trên Ở GÓC NHÌN NGÔI THỨ NHẤT (nói thay {target_name}, tự thú nhận sự thật bựa/sĩ diện/lươn lẹo theo context, xưng 'Tao' hoặc 'Tôi/Mình', ngắn gọn 1-2 câu):"
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
                raw_text = response.text or ""
                cleaned = _clean_cabin_output(raw_text)
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
