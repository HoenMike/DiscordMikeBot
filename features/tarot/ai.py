import asyncio
import json
import re
from typing import List, Optional, Tuple, Dict
from google.genai import types
import config
from core.ai import get_ai_client
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, get_yes_no_verdict, READER_STYLES

# Semaphore giới hạn tối đa 3 request AI đồng thời để tránh 429 Rate Limit
AI_SEMAPHORE = asyncio.Semaphore(3)

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
    reader_style: str = "neutral",
    recent_context: Optional[Dict] = None
) -> str:
    """Xây dựng prompt AI có trí nhớ bạn cũ và yêu cầu trả JSON có cấu trúc."""
    cards_context = _format_cards_context(drawn_cards)
    style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
    persona_prompt = style_info["persona_prompt"]

    memory_prompt = ""
    if recent_context:
        mem_topic = recent_context.get('topic_tag', 'chung')
        mem_mood = recent_context.get('mood_tag', '')
        mem_vibe = f"{mem_topic} ({mem_mood})" if mem_mood else mem_topic
        memory_prompt = f"""
        🧠 NGỮ CẢNH LẦN ĐỌC TRƯỚC (khoảng {recent_context.get('approx_time', 'vài ngày trước')}):
        - Người này từng chiêm nghiệm về chủ đề: [{mem_vibe}], lá bài chủ đạo là [{recent_context.get('last_card_name', '')}].
        🚨 QUY TẮC NHỚ MANG MÁNG: Nếu bạn muốn liên hệ với lần đọc trước, CHỈ ĐƯỢC nhắc lướt qua một cách tự nhiên như người quen nhớ mang máng (ví dụ: 'Lần trước khi nói về chuyện {mem_topic}, năng lượng có phần chông chênh...'). TUYỆT ĐỐI KHÔNG trích dẫn nguyên văn câu hỏi cũ, KHÔNG bịa đặt chi tiết riêng tư.
        """.strip()

    ctx_str = f'\n- Bối cảnh thực tế: "{context}"' if context else ""
    q_str = f'"{question}"' if question else "Tổng quan năng lượng ngày"

    prompt = f"""
    Bạn là Tarot Reader chuyên nghiệp. Hãy đọc quẻ bài cho `{user_name}`.
    {persona_prompt}

    {memory_prompt}

    THÔNG TIN QUẺ BÀI:
    - Người hỏi: `{user_name}` | Câu hỏi: {q_str}{ctx_str}
    - Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá)
    - Danh sách lá bài:
    {cards_context}

    🚨 YÊU CẦU ĐỊNH DẠNG:
    1. Phân loại chủ đề (`topic_tag`): 1 trong các tag `career` (công việc), `love` (tình cảm), `finance` (tài chính), `health` (sức khỏe), `study` (học tập), hoặc `general` (tổng quan).
    2. Đặt tag tâm trạng / năng lượng (`mood_tag`): 1 cụm từ tiếng Việt ngắn gọn mô tả mood/vibe chủ đạo (ví dụ: 'Cày cuốc chăm chỉ', 'Áp lực & Quá tải', 'Chữa lành & Tĩnh lặng', 'Khởi đầu mới bùng nổ', 'Rối bời & Do dự', 'Thăng hoa & Tự tin', 'Thận trọng & Phòng thủ'...).
    3. Tiêu đề vibe ngắn (`summary_headline`): 1 câu tóm tắt cực ngắn (dưới 15 từ) đúc kết thông điệp cốt lõi của quẻ.
    
    Hãy trả lời theo định dạng JSON có cấu trúc sau:
    ```json
    {{
      "topic_tag": "career",
      "mood_tag": "Cày cuốc chăm chỉ",
      "summary_headline": "Tập trung cao độ cho chuyên môn, mài giũa tay nghề và tích lũy thực lực.",
      "conclusion": "Đưa ra câu kết luận trực diện, đúc kết xu hướng trong 1-2 câu súc tích.",
      "cards_analysis": "Phân tích súc tích từng lá bài trong ngữ cảnh câu hỏi.",
      "advice": "Lời khuyên hành động thực tế và thông điệp khích lệ.",
      "full_reading": "Toàn bộ bài giải hoàn chỉnh được format đẹp bằng Markdown, chia rõ các mục 🎯 KẾT LUẬN, 🃏 Ý NGHĨA CÁC LÁ BÀI, 💡 LỜI KHUYÊN & ĐỊNH HƯỚNG."
    }}
    ```
    """.strip()
    return prompt


async def generate_tarot_reading(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str] = None,
    context: Optional[str] = None,
    reader_style: str = "neutral",
    user_name: str = "Bạn",
    recent_context: Optional[Dict] = None
) -> Tuple[str, str, str, str]:
    """
    Gọi AI phân tích quẻ bài với Concurrency Semaphore và Fallback Cascade:
    gemini-3.7-flash ➔ gemini-3.6-flash ➔ gemini-3.5-flash ➔ gemini-3.5-flash-lite ➔ gemini-3.1-flash-lite ➔ gemma-4-31b-it.
    Trả về Tuple: (full_reading_markdown, topic_tag, mood_tag, summary_headline)
    """
    spread_info = SPREAD_DEFINITIONS.get(spread_key, SPREAD_DEFINITIONS["single"])
    spread_name = spread_info["name"]
    prompt = _build_tarot_prompt(spread_key, spread_name, drawn_cards, question, user_name, context, reader_style, recent_context)

    client = get_ai_client()

    models_to_try = getattr(config, "TAROT_FALLBACK_MODELS", [
        config.GEMINI_TAROT_MODEL,
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemma-4-31b-it"
    ])

    seen = set()
    ordered_models = []
    for m in models_to_try:
        if m and m not in seen:
            seen.add(m)
            ordered_models.append(m)

    last_error = None

    async with AI_SEMAPHORE:
        for model_name in ordered_models:
            try:
                print(f"🔮 [Tarot AI] Thử luận giải quẻ '{spread_name}' bằng model '{model_name}'...", flush=True)
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=TAROT_GEN_CONFIG,
                    ),
                    timeout=14.0
                )
                if response and response.text:
                    raw_text = response.text.strip()
                    
                    # Thử parse JSON có cấu trúc
                    topic_tag = "general"
                    mood_tag = "Năng lượng tích cực"
                    summary_headline = ""
                    full_reading = raw_text

                    # Trích xuất JSON từ markdown block nếu có
                    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
                    if json_match:
                        raw_json_str = json_match.group(1)
                    else:
                        raw_json_str = raw_text if raw_text.startswith("{") and raw_text.endswith("}") else ""

                    if raw_json_str:
                        try:
                            parsed = json.loads(raw_json_str)
                            topic_tag = parsed.get("topic_tag", "general")
                            mood_tag = parsed.get("mood_tag", "Cân bằng & Tĩnh tại")
                            summary_headline = parsed.get("summary_headline", "")
                            if "full_reading" in parsed and len(parsed["full_reading"]) > 50:
                                full_reading = parsed["full_reading"]
                            else:
                                full_reading = f"🎯 **KẾT LUẬN & ĐỊNH HƯỚNG:**\n{parsed.get('conclusion', '')}\n\n🃏 **Ý NGHĨA CÁC LÁ BÀI:**\n{parsed.get('cards_analysis', '')}\n\n💡 **LỜI KHUYÊN HÀNH ĐỘNG:**\n{parsed.get('advice', '')}"
                        except Exception:
                            pass

                    # Dọn dẹp lời chào mở đầu nếu có
                    clean_text = re.sub(r"^(.*?(thân mến|thân yêu|chào mừng|chào bạn|dưới đây là|đây là).*?\n+)+", "", full_reading, flags=re.IGNORECASE).strip()
                    print(f"✅ [Tarot AI] Thành công luận giải với model '{model_name}' (Tag: {topic_tag} | Mood: {mood_tag}).", flush=True)
                    return clean_text, topic_tag, mood_tag, summary_headline
            except asyncio.TimeoutError:
                print(f"⏱️ [Tarot AI] Model '{model_name}' phản hồi quá lâu (>14s), chuyển sang model tiếp theo...", flush=True)
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                    print(f"⚠️ [Tarot AI] Model '{model_name}' tạm thời quá tải (503 High Demand), tự động chuyển sang model dự phòng tiếp theo...", flush=True)
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    print(f"⚠️ [Tarot AI] Model '{model_name}' chạm giới hạn quota (429 Rate Limit), tự động chuyển sang model dự phòng tiếp theo...", flush=True)
                else:
                    print(f"⚠️ [Tarot AI] Model '{model_name}' không khả dụng ({type(e).__name__}), chuyển sang model tiếp theo...", flush=True)

    print(f"❌ [Tarot AI] Tất cả các model trong danh sách fallback đều thất bại! Sử dụng bộ luận giải chiêm tinh cổ điển từ điển Tarot...", flush=True)
    fallback_parts = [
        "📖 **BÀI LUẬN GIẢI CHIÊM TINH (TỪ ĐIỂN TAROT CỔ ĐIỂN):**\n"
    ]
    for c in drawn_cards:
        orient_str = "Ngược" if c.is_reversed else "Xuôi"
        meaning = c.card.meaning_reversed if c.is_reversed else c.card.meaning_upright
        kw = c.card.keywords_reversed if c.is_reversed else c.card.keywords_upright
        fallback_parts.append(
            f"**🎴 {c.position_title} — {c.card.name_vi} ({orient_str}):**\n"
            f"• *Từ khóa:* {', '.join(kw)}\n"
            f"• *Ý nghĩa:* {meaning}\n"
        )
    fallback_parts.append(
        "💡 **Lời khuyên tổng kết:** Hãy nhìn nhận thông điệp từ góc độ khách quan, lắng nghe trực giác và đưa ra quyết định phù hợp nhất với hành trình của bạn!"
    )
    return "\n".join(fallback_parts), "general", "Chiêm nghiệm cổ điển", "Thông điệp chiêm tinh cổ điển từ điển Tarot"


async def generate_followup_answer(
    drawn_cards: List[DrawnCard],
    original_question: Optional[str],
    original_reading: str,
    user_followup_question: str,
    reader_style: str = "neutral",
    user_name: str = "Bạn"
) -> str:
    """
    Trả lời câu hỏi đào sâu bổ sung của người dùng dựa trên ngữ cảnh quẻ bài vừa giải.
    """
    cards_context = _format_cards_context(drawn_cards)
    style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
    persona_prompt = style_info["persona_prompt"]

    prompt = f"""
    Bạn là Tarot Reader. Người hỏi `{user_name}` vừa bốc một quẻ bài và có một câu hỏi thắc mắc thêm để làm rõ ý nghĩa.
    {persona_prompt}

    THÔNG TIN QUẺ BÀI ĐÃ RÚT:
    - Câu hỏi ban đầu: "{original_question or 'Tổng quan'}"
    - Các lá bài:
    {cards_context}

    - Tóm tắt bài luận giải trước đó:
    {original_reading[:800]}

    ❓ CÂU HỎI THẮC MẮC BỔ SUNG CỦA `{user_name}`:
    "{user_followup_question}"

    🚨 YÊU CẦU:
    - Trả lời ngắn gọn, trực diện, ấm áp và thấu đáo trong 1-2 đoạn văn (dưới 800 ký tự).
    - Giải thích rõ sự liên kết giữa câu hỏi mới và các lá bài đã xuất hiện.
    """.strip()

    client = get_ai_client()
    async with AI_SEMAPHORE:
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=config.GEMINI_TAROT_MODEL,
                    contents=prompt,
                    config=TAROT_GEN_CONFIG,
                ),
                timeout=12.0
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"⚠️ [Tarot Follow-up] Lỗi trả lời câu hỏi phụ: {e}", flush=True)

    return f"✨ Dựa trên các lá bài đã rút, vũ trụ nhắc nhở bạn hãy giữ tâm thế vững vàng, lắng nghe trực giác bên trong khi đối diện với câu hỏi '{user_followup_question}'."


def recommend_spread_for_question(question: str) -> Tuple[str, str, str]:
    """
    Phân tích từ khóa câu hỏi để gợi ý kiểu trải bài phù hợp nhất.
    Trả về Tuple: (spread_key, spread_name, lý_do_gợi_ý)
    """
    q = (question or "").lower()

    if any(kw in q for kw in ["chọn", "lựa chọn", "a hay b", "hay là", "hoặc", "ngã ba", "đổi việc hay ở lại"]):
        return ("choices", "Trải 2 Lựa Chọn (3 lá)", "Câu hỏi của bạn mang tính chất phân vân giữa 2 ngã rẽ. Trải 2 Lựa Chọn sẽ so sánh trực quan ưu/nhược điểm của từng hướng đi.")

    if any(kw in q for kw in ["có nên", "được không", "thành công không", "yes no", "có hay không", "liệu có"]):
        return ("yes_no", "Trải Bài Yes / No (1 lá)", "Câu hỏi đóng cần một phán quyết dứt khoát. Trải Yes/No sẽ cho bạn câu trả lời nhanh và lời khuyên then chốt.")

    if any(kw in q for kw in ["tình cảm", "crush", "người yêu", "chia tay", "quay lại", "hôn nhân", "tình duyên", "tỏ tình"]):
        return ("ppf", "Quá Khứ - Hiện Tại - Tương Lai (3 lá)", "Vấn đề tình cảm luôn có dòng chảy thời gian và nguồn gốc tâm lý. Trải 3 lá giúp soi chiếu lại hành trình và xu hướng tương lai.")

    if any(kw in q for kw in ["tổng quan", "năm nay", "cuộc đời", "sự nghiệp dài hạn", "vận mệnh", "bức tranh toàn cảnh"]):
        return ("celtic_cross", "Celtic Cross - Thập Tự Celtic (10 lá)", "Vấn đề phức tạp và mang tính bước ngoặt. Celtic Cross là trải bài kinh điển 10 lá phân tích toàn diện mọi khía cạnh ẩn sâu.")

    return ("ppf", "Quá Khứ - Hiện Tại - Tương Lai (3 lá)", "Trải bài 3 lá cổ điển, linh hoạt và phù hợp nhất để xem xét tiến trình của hầu hết mọi vấn đề trong cuộc sống.")

