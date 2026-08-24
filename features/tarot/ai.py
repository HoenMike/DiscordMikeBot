import asyncio
from typing import List, Optional
from google.genai import types
import config
from services.ai_service import get_ai_client
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, get_yes_no_verdict

# Cấu hình AI Tarot: Nhiệt độ 0.7 để ngôn từ mượt mà, trực giác và thấu cảm
TAROT_GEN_CONFIG = types.GenerateContentConfig(
    temperature=config.TAROT_TEMPERATURE,
)


def _format_cards_context(drawn_cards: List[DrawnCard]) -> str:
    """Tạo văn bản mô tả danh sách lá bài rút được để đưa vào prompt."""
    lines = []
    for drawn in drawn_cards:
        orient = "Ngược (Reversed)" if drawn.is_reversed else "Xuôi (Upright)"
        keywords = ", ".join(drawn.current_keywords)
        lines.append(
            f"• [{drawn.position_title}]: Lá '{drawn.card.name_vi}' ({drawn.card.name_en}) - {orient}\n"
            f"  - Từ khóa chính: {keywords}\n"
            f"  - Ý nghĩa biểu tượng: {drawn.card.description}"
        )
    return "\n\n".join(lines)


async def generate_tarot_reading(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str] = None,
    user_name: str = "Bạn"
) -> str:
    """Gọi Gemini AI để tạo bài luận giải Tarot sâu sắc, khách quan và thấu cảm."""
    spread_info = SPREAD_DEFINITIONS.get(spread_key, SPREAD_DEFINITIONS["single"])
    spread_name = spread_info["name"]
    cards_context = _format_cards_context(drawn_cards)

    # 1. Prompt cho kiểu Yes/No
    if spread_key == "yes_no":
        card = drawn_cards[0].card
        is_rev = drawn_cards[0].is_reversed
        badge, verdict_title, _ = get_yes_no_verdict(card, is_rev)

        prompt = f"""
        Bạn là một Tarot reader thông thái, trực giác nhạy bén và thấu cảm.
        Người hỏi: `{user_name}`
        Câu hỏi: "{question}"
        Kiểu trải bài: Yes / No (Hỏi nhanh)
        Phán quyết cơ bản: {badge} - {verdict_title}
        Lá bài rút được:
        {cards_context}

        Hãy đưa ra lời luận giải súc tích (dưới 1500 ký tự) theo cấu trúc markdown sau:
        1. 🔮 **Phán quyết & Năng lượng cốt lõi**: Khẳng định rõ câu trả lời ({badge}) và lý do tại sao lá bài này mang năng lượng đó đối với câu hỏi "{question}".
        2. 🃏 **Biểu tượng lá bài**: Giải thích ngắn gọn hình tượng của lá bài (ở trạng thái {'Ngược' if is_rev else 'Xuôi'}) tác động thế nào đến tình huống.
        3. 💡 **Lời khuyên hành động**: 1-2 câu chỉ rõ người hỏi nên làm gì hoặc cần lưu ý điều gì ngay lúc này để đạt kết quả tốt nhất.
        """

    # 2. Prompt cho kiểu Daily Card
    elif spread_key == "daily":
        prompt = f"""
        Bạn là một Tarot reader giàu tình cảm, tinh tế và truyền cảm hứng tích cực.
        Người nhận thông điệp: `{user_name}`
        Kiểu trải bài: Daily Card (Năng lượng & Thông điệp Ngày Mới)
        Lá bài rút được:
        {cards_context}

        Hãy đưa ra bài luận giải tràn đầy cảm hứng (dưới 1800 ký tự) theo cấu trúc markdown:
        1. 🌌 **Năng lượng ngày mới**: Bức tranh năng lượng bao quát của `{user_name}` trong ngày hôm nay.
        2. 🃏 **Thông điệp lá bài**: Ý nghĩa chi tiết của lá bài mang lại bài học hoặc cơ hội gì.
        3. 💡 **Kim chỉ nam hành động**: Những việc nên làm và những điều nên tránh trong ngày để đón nhận may mắn và giữ tâm thế an yên.
        """

    # 3. Prompt cho kiểu Two Choices (So sánh nhanh - 3 lá)
    elif spread_key == "choices":
        prompt = f"""
        Bạn là một chuyên gia tư vấn Tarot thông thái, khách quan và sâu sắc.
        Người hỏi: `{user_name}`
        Vấn đề phân vân: "{question}"
        Kiểu trải bài: Two Choices (So sánh Nhanh 2 Lựa chọn)
        Các lá bài rút được:
        {cards_context}

        Hãy đưa ra bài phân tích mạch lạc và so sánh rõ ràng (dưới 2500 ký tự) theo cấu trúc markdown:
        1. 🌌 **Bối cảnh & Tâm thế**: Phân tích Lá 1 (Tâm lý và thực trạng hiện tại của `{user_name}`).
        2. 🅰️ **Hướng đi A**: Phân tích Lá 2 (Tiềm năng, cơ hội & bài học nếu chọn A).
        3. 🅱️ **Hướng đi B**: Phân tích Lá 3 (Tiềm năng, cơ hội & bài học nếu chọn B).
        4. ⚖️ **So sánh & Định hướng**: Đặt 2 lựa chọn lên bàn cân và đưa ra lời khuyên thực tế giúp `{user_name}` chọn con đường phù hợp nhất.
        """

    # 4. Prompt cho kiểu Two Paths (So sánh chuyên sâu - 5 lá)
    elif spread_key == "two_paths":
        prompt = f"""
        Bạn là một chuyên gia tư vấn Tarot chiến lược, thông thái và khách quan.
        Người hỏi: `{user_name}`
        Vấn đề phân vân: "{question}"
        Kiểu trải bài: Two Paths (So Sánh Chuyên Sâu 2 Hướng - 5 Lá)
        Các lá bài rút được:
        {cards_context}

        Hãy đưa ra bài phân tích chuyên sâu đa chiều (dưới 3200 ký tự) theo cấu trúc markdown:
        1. 🌌 **Bản chất vấn đề & Tâm thế**: Phân tích Lá 1 (Gốc rễ tình huống và tâm lý người hỏi).
        2. 🅰️ **Phân tích Hướng đi A**:
           - **Thuận lợi & Tiềm năng (Lá 2)**: Điểm mạnh, cơ hội và kết quả tích cực.
           - **Rủi ro & Thách thức (Lá 3)**: Trở ngại tiềm ẩn, điểm yếu cần đề phòng.
        3. 🅱️ **Phân tích Hướng đi B**:
           - **Thuận lợi & Tiềm năng (Lá 4)**: Điểm mạnh, cơ hội và kết quả tích cực.
           - **Rủi ro & Thách thức (Lá 5)**: Trở ngại tiềm ẩn, điểm yếu cần đề phòng.
        4. ⚖️ **Bàn cân so sánh & Lời khuyên quyết định**: So sánh tương quan rủi ro/lợi ích giữa 2 nhánh và đưa ra kim chỉ nam thực tế.
        """

    # 5. Prompt cho các kiểu trải bài khác (Single, PPF, MBS, Horseshoe, Celtic Cross)
    else:
        question_text = f'"{question}"' if question else "Không có câu hỏi cụ thể (Xem năng lượng tổng thể)"
        prompt = f"""
        Bạn là một Tarot reader chuyên nghiệp, thấu cảm sâu sắc, khách quan và giàu triết lý nhân sinh.
        Người hỏi: `{user_name}`
        Câu hỏi / Chủ đề: {question_text}
        Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá)
        Các lá bài rút được:
        {cards_context}

        🚨 NGUYÊN TẮC LUẬN GIẢI:
        - Tôn trọng tự do ý chí (Free Will) của con người: Tarot là tấm gương phản chiếu tiềm thức và xu hướng, không phải định mệnh bất biến.
        - Giọng văn thấu cảm, truyền động lực, mang tính tư vấn tâm lý tích cực, tuyệt đối KHÔNG hù dọa, KHÔNG mê tín dị đoan.
        - Kết nối chặt chẽ ý nghĩa từng lá bài vào câu hỏi cụ thể của người dùng.

        BỐ CỤC BÀI VIẾT (Markdown chuyên nghiệp):
        1. 🔮 **Tổng quan bức tranh năng lượng**: Đánh giá bao quát trạng thái hiện tại và xu hướng dòng chảy năng lượng.
        2. 🃏 **Luận giải chi tiết từng vị trí**: Phân tích ý nghĩa từng lá bài tại vị trí tương ứng (chú ý chiều Xuôi/Ngược).
        3. 🔗 **Sợi dây liên kết & Diễn biến**: Sự tương tác qua lại giữa các lá bài tạo nên câu chuyện tổng thể như thế nào.
        4. 💡 **Lời khuyên hành động thực tế (Actionable Advice)**: Hướng giải quyết tích cực, lời khuyên thực tế để `{user_name}` làm chủ tình huống của mình.
        """

    print(f"🔮 [Tarot AI] Đang phân tích quẻ bài '{spread_name}' cho `{user_name}`...", flush=True)
    try:
        response = await asyncio.to_thread(
            get_ai_client().models.generate_content,
            model=config.GEMINI_TAROT_MODEL,
            contents=prompt,
            config=TAROT_GEN_CONFIG,
        )
        print(f"✅ [Tarot AI] Đã hoàn thành luận giải quẻ bài.", flush=True)
        return response.text
    except Exception as e:
        print(f"❌ [Tarot AI] Lỗi khi gọi AI luận giải: {e}", flush=True)
        return (
            "⚠️ **Lỗi kết nối AI:** Không thể nhận bài luận giải chi tiết từ AI lúc này.\n"
            "Tuy nhiên bạn vẫn có thể dựa vào các từ khóa và hình ảnh lá bài phía trên để tự chiêm nghiệm!"
        )
