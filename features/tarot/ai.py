import asyncio
from typing import List, Optional
from google.genai import types
import config
from core.ai import get_ai_client
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, get_yes_no_verdict, READER_STYLES

# Cấu hình AI Tarot: Nhiệt độ 0.65 để câu trả lời sinh động, giàu cá tính
TAROT_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.65,
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
    user_name: str,
    context: Optional[str] = None,
    reader_style: str = "neutral"
) -> str:
    """Xây dựng prompt ngắn gọn, kết luận ngay trên đầu, súc tích, trực diện và tràn đầy năng lượng xây dựng tích cực."""
    cards_context = _format_cards_context(drawn_cards)
    style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
    persona_prompt = style_info["persona_prompt"]

    common_rules = f"""
    🚨 NGUYÊN TẮC LUẬN GIẢI BẮT BUỘC:
    1. TUYỆT ĐỐI KHÔNG xưng hô mở đầu (như "Chào bạn...", "Tên thân mến...", "Dưới đây là..."). BẮT ĐẦU NGAY LẬP TỨC bằng tiêu đề mục 1.
    2. {persona_prompt}
    """.strip()

    # Xử lý thông tin bối cảnh
    ctx_str = f'\n- Bối cảnh / Hoàn cảnh thực tế của `{user_name}`: "{context}"\n(Hãy kết hợp chặt chẽ bối cảnh này với các lá bài để đưa ra lời khuyên cá nhân hóa, sắc bén và chính xác nhất).' if context else ""
    q_str = f'"{question}"' if question else "Tổng quan năng lượng"

    # 1. Prompt cho kiểu Yes/No (1 lá)
    if spread_key == "yes_no":
        card = drawn_cards[0].card
        is_rev = drawn_cards[0].is_reversed
        badge, verdict_title, _ = get_yes_no_verdict(card, is_rev)

        return f"""
        Bạn là Tarot reader chuyên nghiệp và giàu lòng thấu cảm. Hãy trả lời cực kỳ ngắn gọn, súc tích (dưới 600 ký tự).
        Người hỏi: `{user_name}` | Câu hỏi: "{question}"{ctx_str}
        Phán quyết: {badge} - {verdict_title}
        Lá bài: {cards_context}

        {common_rules}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN**: Khẳng định rõ câu trả lời ({badge}) và thông điệp chốt hạ trong 1-2 câu ngắn, mang tính xây dựng.
        2. 🃏 **Ý NGHĨA LÁ BÀI**: Lá bài mang ý nghĩa gì và mang lại gợi ý gì cho câu hỏi của `{user_name}`.
        3. 💡 **LỜI KHUYÊN**: Hướng hành động thực tế và thông điệp khích lệ.
        """.strip()

    # 2. Prompt cho kiểu Daily Card (1 lá)
    elif spread_key == "daily":
        if question:
            return f"""
            Bạn là Tarot reader truyền cảm hứng và tinh tế. Hãy giải mã lá bài để trả lời trực tiếp cho câu hỏi trong ngày của người hỏi (dưới 700 ký tự).
            Người nhận: `{user_name}` | Câu hỏi / Định hướng: "{question}"{ctx_str}
            Lá bài:
            {cards_context}

            {common_rules}

            Cấu trúc trả lời:
            1. 🎯 **TRẢ LỜI & ĐỊNH HƯỚNG**: Dựa vào năng lượng của lá bài, trả lời trực diện câu hỏi "{question}" trong 1-2 câu súc tích.
            2. 🃏 **Ý NGHĨA LÁ BÀI**: Tại sao lá bài lại đưa ra gợi ý/lựa chọn này dưới góc nhìn năng lượng ngày.
            3. 💡 **GỢI Ý HÀNH ĐỘNG**: Lời khuyên cụ thể và điểm lưu ý thực tế để đạt kết quả tốt nhất.
            """.strip()
        else:
            return f"""
            Bạn là Tarot reader truyền cảm hứng. Hãy đưa ra thông điệp ngày mới ngắn gọn, tích cực (dưới 700 ký tự).
            Người nhận: `{user_name}`{ctx_str} | Lá bài:
            {cards_context}

            {common_rules}

            Cấu trúc trả lời:
            1. 🎯 **TỔNG QUAN NGÀY MỚI**: Năng lượng cốt lõi và kết luận thông điệp hôm nay trong 1-2 câu.
            2. 🃏 **Ý NGHĨA LÁ BÀI**: Cơ hội hoặc điểm lưu ý cần chuyển hóa trong ngày.
            3. 💡 **KIM CHỈ NAM**: 1 điều nên phát huy và 1 điều nên lưu ý.
            """.strip()

    # 3. Prompt cho kiểu Two Choices (3 lá)
    elif spread_key == "choices":
        return f"""
        Bạn là Tarot reader định hướng. Hãy so sánh 2 lựa chọn cực kỳ súc tích, trực diện, khích lệ (dưới 1200 ký tự).
        Người hỏi: `{user_name}` | Vấn đề phân vân: "{question}"{ctx_str}
        Lá bài:
        {cards_context}

        {common_rules}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & ĐỊNH HƯỚNG CHÍNH**: Đưa ra nhận định tổng quan và gợi ý hướng đi thuận lợi hơn trong 2 câu.
        2. 🃏 **PHÂN TÍCH NHANH CÁC LÁ BÀI**:
           - **Bối cảnh (Lá 1)**: Tâm thế và thực trạng hiện tại.
           - **Hướng A (Lá 2)**: Tiềm năng & điều cần chuẩn bị nếu chọn A.
           - **Hướng B (Lá 3)**: Tiềm năng & điều cần chuẩn bị nếu chọn B.
        3. 💡 **TẠI SAO & LỜI KHUYÊN**: Đúc kết lý do và giải pháp hành động tốt nhất.
        """.strip()

    # 4. Prompt cho kiểu Two Paths (5 lá)
    elif spread_key == "two_paths":
        return f"""
        Bạn là Tarot reader chuyên sâu. Hãy phân tích 2 lựa chọn rõ ràng, công tâm, mang tính định hướng phát triển (dưới 1600 ký tự).
        Người hỏi: `{user_name}` | Vấn đề phân vân: "{question}"{ctx_str}
        Lá bài:
        {cards_context}

        {common_rules}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & ĐỊNH HƯỚNG CHÍNH**: Kết luận hướng đi tối ưu và định hướng tổng quan trong 2-3 câu.
        2. 🃏 **Ý NGHĨA CÁC LÁ TRONG NGỮ CẢNH**:
           - **Bối cảnh chung (Lá 1)**: Nguồn gốc phân vân & bài học cần học.
           - **Hướng A (Lá 2 & 3)**: Thuận lợi và điểm cần lưu ý của Hướng A.
           - **Hướng B (Lá 4 & 5)**: Thuận lợi và điểm cần lưu ý của Hướng B.
        3. 💡 **ĐÚC KẾT TẠI SAO & HÀNH ĐỘNG**: Giải thích lý do và các bước chuẩn bị thực tế để tự tin ra quyết định.
        """.strip()

    # 5. Prompt cho các kiểu trải bài khác (Single, PPF, MBS, Horseshoe, Celtic Cross)
    else:
        return f"""
        Bạn là Tarot reader chuyên nghiệp, thấu cảm và mang lại năng lượng tích cực. Hãy luận giải súc tích, cô đọng, đi thẳng vào trọng tâm (dưới 1800 ký tự).
        Người hỏi: `{user_name}` | Câu hỏi: {q_str}{ctx_str}
        Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá)
        Lá bài rút được:
        {cards_context}

        {common_rules}

        Cấu trúc trả lời:
        1. 🎯 **KẾT LUẬN & TỔNG QUAN**: Trả lời trực diện câu hỏi của `{user_name}`, đúc kết xu hướng và thông điệp cốt lõi trong 2-3 câu ngắn mang tính xây dựng.
        2. 🃏 **Ý NGHĨA CÁC LÁ BÀI TRONG NGỮ CẢNH CÂU HỎI**: Tóm tắt từng lá (1-2 câu/lá), nêu rõ thông điệp và điểm nghẽn cần tháo gỡ đối với trường hợp của `{user_name}`.
        3. 💡 **ĐÚC KẾT & LỜI KHUYÊN TẠI SAO**: Giải thích tại sao có thông điệp này và hướng dẫn các bước hành động cụ thể để người hỏi vượt qua thử thách, đạt được mục tiêu.
        """.strip()


async def generate_tarot_reading(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str] = None,
    context: Optional[str] = None,
    reader_style: str = "neutral",
    user_name: str = "Bạn"
) -> str:
    """
    Gọi AI phân tích quẻ bài với chuỗi mô hình dự phòng (Fallback Cascade):
    gemini-3.7-flash ➔ gemini-3.6-flash ➔ gemini-3.5-flash ➔ gemini-3.5-flash-lite ➔ gemini-3.1-flash-lite ➔ gemma-4-31b-it.
    """
    spread_info = SPREAD_DEFINITIONS.get(spread_key, SPREAD_DEFINITIONS["single"])
    spread_name = spread_info["name"]
    prompt = _build_tarot_prompt(spread_key, spread_name, drawn_cards, question, user_name, context, reader_style)

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
            # Timeout tối đa 12s cho mỗi model để nếu nghẽn/chậm thì lập tức fallback, không bắt người dùng chờ
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=TAROT_GEN_CONFIG,
                ),
                timeout=12.0
            )
            if response and response.text:
                import re
                raw_text = response.text
                clean_text = re.sub(r"^(.*?(thân mến|thân yêu|chào mừng|chào bạn|dưới đây là|đây là).*?\n+)+", "", raw_text, flags=re.IGNORECASE).strip()
                print(f"✅ [Tarot AI] Thành công luận giải với model '{model_name}'.", flush=True)
                return clean_text
        except asyncio.TimeoutError:
            print(f"⏱️ [Tarot AI] Model '{model_name}' phản hồi quá lâu (>12s), lập tức chuyển sang model tiếp theo...", flush=True)
        except Exception as e:
            last_error = e
            print(f"⚠️ [Tarot AI] Model '{model_name}' gặp sự cố ({type(e).__name__}): {e}. Chuyển sang model tiếp theo...", flush=True)

    print(f"❌ [Tarot AI] Tất cả các model trong danh sách fallback đều thất bại! Lỗi cuối: {last_error}", flush=True)
    return (
        "🌌 **Tín hiệu vũ trụ bị gián đoạn:** Nguồn năng lượng từ vũ trụ hiện đang bị nhiễu động tạm thời.\n"
        "Tuy nhiên bạn vẫn có thể dựa vào hình ảnh và các lá bài phía trên để tự chiêm nghiệm câu trả lời cho riêng mình!"
    )
