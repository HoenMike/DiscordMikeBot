import asyncio
from typing import List, Optional
from google.genai import types
import config
from services.ai_service import get_ai_client
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, get_yes_no_verdict

# Cấu hình AI Tarot: Nhiệt độ 0.5 để câu trả lời súc tích, tập trung, chuẩn xác
TAROT_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.5,
)


def _format_cards_context(drawn_cards: List[DrawnCard]) -> str:
    """Tạo văn bản mô tả danh sách lá bài rút được cô đọng, giàu dữ kiện."""
    lines = []
    for drawn in drawn_cards:
        orient = "Ngược" if drawn.is_reversed else "Xuôi"
        keywords = ", ".join(drawn.current_keywords[:2])
        lines.append(
            f"• [{drawn.position_title}]: {drawn.card.name_vi} ({drawn.card.name_en}) - [{orient}] (Từ khóa: {keywords})"
        )
    return "\n".join(lines)


def _build_tarot_prompt(
    spread_key: str,
    spread_name: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str],
    user_name: str
) -> str:
    """Xây dựng prompt ngắn gọn, kết luận ngay trên đầu, súc tích và trực diện."""
    cards_context = _format_cards_context(drawn_cards)
    q_str = f'"{question}"' if question else "Không có câu hỏi cụ thể (Xem năng lượng tổng quan)"

    # 1. Prompt cho kiểu Yes/No (1 lá)
    if spread_key == "yes_no":
        card = drawn_cards[0].card
        is_rev = drawn_cards[0].is_reversed
        badge, verdict_title, _ = get_yes_no_verdict(card, is_rev)

        return f"""
        Bạn là Tarot reader chuyên nghiệp. Hãy trả lời cực kỳ ngắn gọn, súc tích (dưới 600 ký tự).
        Người hỏi: `{user_name}` | Câu hỏi: "{question}"
        Phán quyết: {badge} - {verdict_title}
        Lá bài: {cards_context}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN**: Khẳng định rõ câu trả lời ({badge}) và thông điệp chốt hạ trong 1-2 câu.
        2. 🃏 **Ý NGHĨA LÁ BÀI**: Lá bài này mang ý nghĩa gì và trong câu hỏi của `{user_name}` nó thể hiện điều gì.
        3. 💡 **LỜI KHUYÊN**: Lời khuyên hành động thực tế ngắn gọn.
        """.strip()

    # 2. Prompt cho kiểu Daily Card (1 lá)
    elif spread_key == "daily":
        return f"""
        Bạn là Tarot reader. Hãy đưa ra thông điệp ngày mới ngắn gọn, tích cực (dưới 700 ký tự).
        Người nhận: `{user_name}` | Lá bài:
        {cards_context}

        Cấu trúc trả lời:
        1. 🎯 **TỔNG QUAN NGÀY MỚI**: Năng lượng cốt lõi và kết luận thông điệp hôm nay trong 1-2 câu.
        2. 🃏 **Ý NGHĨA LÁ BÀI**: Lá bài nhắc nhở cơ hội hoặc lưu ý gì cho ngày hôm nay.
        3. 💡 **KIM CHỈ NAM**: 1 điều nên làm và 1 điều nên tránh.
        """.strip()

    # 3. Prompt cho kiểu Two Choices (3 lá)
    elif spread_key == "choices":
        return f"""
        Bạn là Tarot reader. Hãy so sánh 2 lựa chọn cực kỳ súc tích, trực diện (dưới 1200 ký tự).
        Người hỏi: `{user_name}` | Vấn đề phân vân: "{question}"
        Lá bài:
        {cards_context}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & ĐỊNH HƯỚNG CHÍNH (ĐẶT TRÊN ĐẦU)**: Đưa ra nhận định tổng quan và nghiêng về hướng nào trong 2 câu.
        2. 🃏 **PHÂN TÍCH NHANH CÁC LÁ BÀI**:
           - **Bối cảnh (Lá 1)**: Thực trạng hiện tại.
           - **Hướng A (Lá 2)**: Ý nghĩa lá bài & điều sẽ xảy ra nếu chọn A.
           - **Hướng B (Lá 3)**: Ý nghĩa lá bài & điều sẽ xảy ra nếu chọn B.
        3. 💡 **TẠI SAO & LỜI KHUYÊN**: Đúc kết ngắn gọn lý do tại sao nên chọn hướng đó.
        """.strip()

    # 4. Prompt cho kiểu Two Paths (5 lá)
    elif spread_key == "two_paths":
        return f"""
        Bạn là Tarot reader. Hãy phân tích 2 lựa chọn ngắn gọn, rõ ràng, không viết dài dòng (dưới 1600 ký tự).
        Người hỏi: `{user_name}` | Vấn đề phân vân: "{question}"
        Lá bài:
        {cards_context}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & ĐỊNH HƯỚNG CHÍNH (ĐẶT TRÊN ĐẦU)**: Kết luận dứt khoát hướng đi tốt hơn và tổng quan tình huống trong 2-3 câu.
        2. 🃏 **Ý NGHĨA CÁC LÁ TRONG NGỮ CẢNH**:
           - **Bối cảnh (Lá 1)**: Tâm thế và nguyên nhân phân vân.
           - **Hướng A (Lá 2 & 3)**: Thuận lợi và rủi ro nếu chọn A.
           - **Hướng B (Lá 4 & 5)**: Thuận lợi và rủi ro nếu chọn B.
        3. 💡 **ĐÚC KẾT TẠI SAO & HÀNH ĐỘNG**: Giải thích tại sao lại có kết luận trên và gợi ý các bước đi tiếp theo.
        """.strip()

    # 5. Prompt cho các kiểu trải bài khác (Single, PPF, MBS, Horseshoe, Celtic Cross)
    else:
        return f"""
        Bạn là Tarot reader chuyên nghiệp. Hãy luận giải súc tích, cô đọng, đi thẳng vào trọng tâm, KHÔNG viết dài dòng lê thê (dưới 1800 ký tự).
        Người hỏi: `{user_name}` | Câu hỏi: {q_str}
        Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá)
        Lá bài rút được:
        {cards_context}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & TỔNG QUAN (ĐẶT TRÊN ĐẦU)**: Trả lời trực diện câu hỏi của `{user_name}`, tổng quan quẻ bài này báo hiệu điều gì trong 2-3 câu ngắn.
        2. 🃏 **Ý NGHĨA CÁC LÁ BÀI TRONG NGỮ CẢNH CÂU HỎI**: Tóm tắt ngắn gọn từng lá (1-2 câu/lá) nói lên điều gì đối với trường hợp của `{user_name}`.
        3. 💡 **ĐÚC KẾT & LỜI KHUYÊN TẠI SAO**: Giải thích ngắn gọn tại sao lại có kết luận đó và hướng hành động thực tế.
        """.strip()


async def generate_tarot_reading(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str] = None,
    user_name: str = "Bạn"
) -> str:
    """
    Gọi AI phân tích quẻ bài với chuỗi mô hình dự phòng (Fallback Cascade):
    gemini-3.7-flash ➔ gemini-3.6-flash ➔ gemini-3.5-flash ➔ gemini-3.5-flash-lite ➔ gemini-3.1-flash-lite ➔ gemma-4-31b-it.
    """
    spread_info = SPREAD_DEFINITIONS.get(spread_key, SPREAD_DEFINITIONS["single"])
    spread_name = spread_info["name"]
    prompt = _build_tarot_prompt(spread_key, spread_name, drawn_cards, question, user_name)

    client = get_ai_client()

    models_to_try = getattr(config, "TAROT_FALLBACK_MODELS", [
        config.GEMINI_TAROT_MODEL,
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemma-4-31b-it"
    ])

    # Loại bỏ trùng lặp giữ nguyên thứ tự
    seen = set()
    ordered_models = []
    for m in models_to_try:
        if m and m not in seen:
            seen.add(m)
            ordered_models.append(m)

    last_error = None
    for model_name in ordered_models:
        try:
            print(f"🔮 [Tarot AI] Thử luận giải quẻ '{spread_name}' bằng model '{model_name}'...", flush=True)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config=TAROT_GEN_CONFIG,
            )
            if response and response.text:
                print(f"✅ [Tarot AI] Thành công luận giải với model '{model_name}'.", flush=True)
                return response.text
        except Exception as e:
            last_error = e
            print(f"⚠️ [Tarot AI] Model '{model_name}' gặp sự cố ({type(e).__name__}): {e}. Chuyển sang model tiếp theo...", flush=True)
            await asyncio.sleep(0.5)

    print(f"❌ [Tarot AI] Tất cả các model trong danh sách fallback đều thất bại! Lỗi cuối: {last_error}", flush=True)
    return (
        "⚠️ **Lỗi kết nối AI:** Không thể nhận bài luận giải chi tiết từ AI lúc này do lưu lượng máy chủ tăng cao.\n"
        "Tuy nhiên bạn vẫn có thể dựa vào các từ khóa và hình ảnh lá bài phía trên để tự chiêm nghiệm!"
    )
