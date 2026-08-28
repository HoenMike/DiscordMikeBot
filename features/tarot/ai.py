import asyncio
import json
import re
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field
from google.genai import types
import config
from core.ai import get_ai_client
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, get_yes_no_verdict, READER_STYLES

# Semaphore giới hạn tối đa 3 request AI đồng thời để tránh 429 Rate Limit
AI_SEMAPHORE = asyncio.Semaphore(3)


class TarotAIResponseSchema(BaseModel):
    """Schema chuẩn hóa cho đầu ra JSON từ Gemini AI."""
    topic_tag: str = Field(description="Phân loại chủ đề: career, love, finance, health, study, general", default="general")
    mood_tag: str = Field(description="Tag vibe/tâm trạng chủ đạo bằng tiếng Việt", default="Cân bằng & Tĩnh tại")
    summary_headline: str = Field(description="Tiêu đề vibe ngắn dưới 15 từ", default="")
    conclusion: str = Field(description="Kết luận trực diện, đúc kết xu hướng trong 1-2 câu", default="")
    cards_analysis: str = Field(description="Phân tích súc tích từng lá bài trong ngữ cảnh", default="")
    advice: str = Field(description="Lời khuyên hành động thực tế và thông điệp khích lệ", default="")
    full_reading: str = Field(description="Toàn bộ bài giải hoàn chỉnh bằng Markdown, chia rõ các mục", default="")


# Cấu hình AI Tarot chính (buộc trả về JSON có cấu trúc an toàn, giới hạn thinking_budget để tránh timeout)
TAROT_GEN_CONFIG = types.GenerateContentConfig(
    temperature=0.65,
    response_mime_type="application/json",
    response_schema=TarotAIResponseSchema,
    thinking_config=types.ThinkingConfig(thinking_budget=1024),
)

# Cấu hình dự phòng nhẹ nếu model không hỗ trợ schema hoặc thinking config
TAROT_GEN_CONFIG_FALLBACK = types.GenerateContentConfig(
    temperature=0.65,
    response_mime_type="application/json",
)

# Cấu hình dành cho câu hỏi phụ (trả lời trực tiếp dạng văn bản tự do)
TAROT_FOLLOWUP_CONFIG = types.GenerateContentConfig(
    temperature=0.65,
    thinking_config=types.ThinkingConfig(thinking_budget=1024),
)


def _format_cards_context(drawn_cards: List[DrawnCard]) -> str:
    """Tạo văn bản mô tả danh sách lá bài rút được cô đọng, giàu dữ kiện chuẩn Tarot."""
    lines = []
    for drawn in drawn_cards:
        orient = "Ngược" if drawn.is_reversed else "Xuôi"
        kw = drawn.card.keywords_reversed if drawn.is_reversed else drawn.card.keywords_upright
        keywords_str = ", ".join(kw)
        lines.append(
            f"• [{drawn.position_title}]: {drawn.card.name_vi} ({drawn.card.name_en}) - [{orient}]\n"
            f"  - Biểu tượng cốt lõi: {drawn.card.description}\n"
            f"  - Từ khóa trạng thái ({orient}): {keywords_str}"
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
    Bạn là Tarot Reader chuyên nghiệp và am tường triết lý 78 lá bài Tarot Rider-Waite.
    Hãy đọc quẻ bài cho `{user_name}` dựa trên đúng ý nghĩa biểu tượng của các lá bài được rút.

    {persona_prompt}

    {memory_prompt}

    THÔNG TIN QUẺ BÀI:
    - Người hỏi: `{user_name}` | Câu hỏi: {q_str}{ctx_str}
    - Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá)
    - Danh sách lá bài & Ý nghĩa biểu tượng chuẩn:
    {cards_context}

    🚨 NGUYÊN TẮC GIẢI BÀI BẮT BUỘC (QUAN TRỌNG):
    1. ĐÚNG BẢN CHẤT Ý NGHĨA TAROT: Cả 3 Persona (Orion, Celeste, Jester) đều phải giải đúng ý nghĩa nguyên bản của lá bài (ví dụ: The Empress Ngược là tắc nghẽn sáng tạo, thiếu chăm sóc bản thân, phụ thuộc cảm xúc; KHÔNG PHẢI lười biếng hay xúc phạm người hỏi).
    2. SỰ KHÁC BIỆT CHỈ Ở PHONG CÁCH DIỄN ĐẠT:
       - Orion: phân tích điềm tĩnh, triết lý, thực tế và sâu sắc.
       - Celeste: vỗ về, chữa lành, dịu dàng và tìm ánh sáng hy vọng.
       - Jester: dí dỏm, tếu táo, trào phúng vui tươi nhưng mang tính xây dựng, tuyệt đối KHÔNG công kích cá nhân, KHÔNG tiêu cực hóa độc hại.
    3. Mọi lá bài ngược (Reversed) là lời nhắc nhở nhẹ nhàng để cân bằng lại năng lượng bên trong, luôn kết thúc bằng lời khuyên và động lực tích cực.

    🚨 YÊU CẦU ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC TRẢ JSON CHUẨN):
    1. `topic_tag`: 1 trong các tag `career` (công việc), `love` (tình cảm), `finance` (tài chính), `health` (sức khỏe), `study` (học tập), hoặc `general` (tổng quan).
    2. `mood_tag`: 1 cụm từ tiếng Việt ngắn gọn mô tả vibe/tâm trạng chủ đạo (ví dụ: 'Cày cuốc chăm chỉ', 'Áp lực & Quá tải', 'Chữa lành & Tĩnh lặng', 'Khởi đầu mới bùng nổ', 'Rối bời & Do dự', 'Thăng hoa & Tự tin', 'Thận trọng & Phòng thủ'...).
    3. `summary_headline`: 1 câu tóm tắt cực ngắn (dưới 15 từ) đúc kết thông điệp cốt lõi của quẻ.
    4. `conclusion`: Đưa ra câu kết luận trực diện, đúc kết xu hướng trong 1-2 câu súc tích.
    5. `cards_analysis`: Phân tích súc tích từng lá bài trong ngữ cảnh câu hỏi, mỗi lá BẮT BUỘC có gạch đầu dòng '• **Tên lá bài**:' và xuống hàng riêng biệt.
    6. `advice`: Lời khuyên hành động thực tế, thông thái và khích lệ người hỏi.
    7. `full_reading`: Toàn bộ bài giải hoàn chỉnh dạng Markdown, BẮT BUỘC phân tách các mục rõ ràng bằng 2 dấu xuống dòng (\\n\\n):
       🎯 **KẾT LUẬN & TỔNG QUAN:**
       (Nội dung kết luận)

       🃏 **Ý NGHĨA CÁC LÁ BÀI:**
       • **[Tên lá bài 1]**: (Phân tích)
       • **[Tên lá bài 2]**: (Phân tích)

       💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
       (Nội dung lời khuyên)
    """.strip()
    return prompt


def _clean_and_format_tarot_markdown(text: str) -> str:
    """
    Chuẩn hóa cấu trúc Markdown bài giải Tarot:
    - Loại bỏ ký tự thừa hoặc tag in đậm bị treo (dangling **).
    - Chuẩn hóa các đề mục icon chính (🎯, 🃏, 💡, 🔮, ⚡, 📖, 🎭, 💖, ✨).
    - Giữ nguyên các dấu gạch nối giữa dòng (' - Ngược', 'A - B') và chỉ chuyển đổi gạch đầu dòng.
    """
    if not text:
        return ""

    t = text.strip()

    # 1. Loại bỏ các ký tự đánh dấu heading Markdown (#, ##, ###) ở đầu dòng
    t = re.sub(r"^[ \t]*#+[ \t]*", "", t, flags=re.MULTILINE)

    # 2. Xóa các dòng rác chỉ chứa dấu sao hoặc dấu cách
    t = re.sub(r"^\s*\*+\s*$", "", t, flags=re.MULTILINE)

    icons = "🎯🃏💡🔮⚡📖🎭💖✨"

    # 3a. Chèn 2 dòng trống trước các icon chính nếu chúng bị dính liền vào câu trước
    t = re.sub(rf"(?<!\A)(?<!\n)\s*([{icons}])", r"\n\n\1", t)

    # 3b. Chuẩn hóa dòng tiêu đề chứa icon: tách tiêu đề và nội dung cùng dòng nếu có
    def _fix_header_line(line: str) -> str:
        m = re.match(rf"^\s*([{icons}])\s*(.*)$", line)
        if not m:
            return line
        icon = m.group(1)
        rest = m.group(2).strip()

        colon_pos = rest.find(":") if ":" in rest else -1
        if colon_pos != -1:
            raw_title = rest[:colon_pos].strip()
            after_colon = rest[colon_pos + 1:].strip()
            clean_title = re.sub(r"[*]", "", raw_title).strip()
            if clean_title:
                res = f"{icon} **{clean_title}:**"
                if after_colon:
                    after_colon = re.sub(r"^\*+\s*", "", after_colon).strip()
                    res += f"\n{after_colon}"
                return res

        clean_title = re.sub(r"[*]", "", rest).strip()
        return f"{icon} **{clean_title}:**" if clean_title else icon

    lines = t.split("\n")
    processed_lines = [_fix_header_line(l) for l in lines]
    t = "\n".join(processed_lines)

    # 4. Chuẩn hóa gạch đầu dòng: Chỉ chuyển đổi dấu '-', '*', '+' ở ĐẦU DÒNG thành bullet '• '
    # TUYỆT ĐỐI không thay thế dấu '-' ở giữa dòng (ví dụ: ' - Ngược' hay 'A - B')
    t = re.sub(r"^[ \t]*[-*+][ \t]+", "• ", t, flags=re.MULTILINE)

    # 5. Dọn dẹp dòng rác chỉ chứa dấu sao một lần nữa
    t = re.sub(r"^\s*\*+\s*$", "", t, flags=re.MULTILINE)

    # 6. Gom bớt các dòng trống liên tiếp (> 2 dòng thành 2 dòng)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


def parse_tarot_ai_response(raw_text: str) -> Tuple[str, str, str, str]:
    """
    Phân tích và trích xuất dữ liệu an toàn từ phản hồi của Gemini AI.
    Sử dụng cơ chế đa tầng (Direct JSON -> Regex Fallback -> Text Cleaning)
    đảm bảo 100% không bao giờ làm lộ mã JSON thô ra giao diện người dùng Discord.
    Trả về Tuple: (full_reading_markdown, topic_tag, mood_tag, summary_headline)
    """
    if not raw_text:
        return "", "general", "Năng lượng tích cực", ""

    text = raw_text.strip()

    # Giá trị mặc định
    topic_tag = "general"
    mood_tag = "Năng lượng tích cực"
    summary_headline = ""
    full_reading = ""

    # Bước 1: Trích xuất khối JSON candidate nếu có
    json_candidate = text
    match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if match:
        json_candidate = match.group(1).strip()
    else:
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            json_candidate = text[first_brace:last_brace + 1].strip()

    parsed_dict: Optional[Dict[str, Any]] = None

    # Bước 2: Thử parse trực tiếp bằng json.loads
    try:
        data = json.loads(json_candidate)
        if isinstance(data, dict):
            parsed_dict = data
    except Exception:
        pass

    # Bước 3: Fallback Regex Field Extraction nếu json.loads thất bại (do unescaped quotes hoặc format lỗi)
    if parsed_dict is None and ("{" in text or '"topic_tag"' in text or '"full_reading"' in text):
        extracted = {}
        keys = [
            "topic_tag",
            "mood_tag",
            "summary_headline",
            "conclusion",
            "cards_analysis",
            "advice",
            "full_reading"
        ]
        for i, key in enumerate(keys):
            pattern = rf'"{key}"\s*:\s*"'
            pos = re.search(pattern, json_candidate)
            if not pos:
                continue
            start_val = pos.end()
            next_keys = keys[i + 1:]
            end_val = -1
            if next_keys:
                next_pattern = "|".join(next_keys)
                next_match = re.search(rf'",?\s*\n\s*"(?:{next_pattern})"\s*:', json_candidate[start_val:])
                if next_match:
                    end_val = start_val + next_match.start()
            if end_val == -1:
                end_match = re.search(r'"\s*\n\s*\}', json_candidate[start_val:])
                if end_match:
                    end_val = start_val + end_match.start()
                else:
                    last_quote = json_candidate.rfind('"')
                    end_val = last_quote if last_quote > start_val else len(json_candidate)

            val = json_candidate[start_val:end_val]
            val = val.replace(r"\n", "\n").replace(r'\"', '"').replace(r"\\", "\\").strip()
            extracted[key] = val

        if any(extracted.values()):
            parsed_dict = extracted

    # Bước 4: Chuyển đổi dữ liệu từ parsed_dict thành bài đọc và metadata
    if parsed_dict:
        # Xử lý topic_tag
        raw_topic = parsed_dict.get("topic_tag", "general")
        topic_tag = str(raw_topic).strip().strip('"').strip() or "general"

        # Xử lý mood_tag
        raw_mood = parsed_dict.get("mood_tag", "Cân bằng & Tĩnh tại")
        mood_tag = str(raw_mood).strip().strip('"').strip() or "Cân bằng & Tĩnh tại"

        # Xử lý summary_headline
        raw_headline = parsed_dict.get("summary_headline", "")
        summary_headline = str(raw_headline).strip().strip('"').strip()

        # Xử lý full_reading
        raw_full = parsed_dict.get("full_reading", "")
        if isinstance(raw_full, list):
            raw_full = "\n\n".join(str(item) for item in raw_full)
        else:
            raw_full = str(raw_full).strip()

        # Tái tạo bài đọc có cấu trúc từ các trường thành phần
        conc = parsed_dict.get("conclusion", "")
        if isinstance(conc, list):
            conc = "\n".join(str(c) for c in conc)
        conc = str(conc).strip()

        cards_an = parsed_dict.get("cards_analysis", "")
        if isinstance(cards_an, list):
            formatted_cards = []
            for item in cards_an:
                if isinstance(item, dict):
                    c_name = item.get("card_name", item.get("name", ""))
                    c_meaning = item.get("meaning", item.get("analysis", ""))
                    formatted_cards.append(f"• **{c_name}**: {c_meaning}" if c_name else f"• {c_meaning}")
                else:
                    formatted_cards.append(f"• {item}")
            cards_an = "\n".join(formatted_cards)
        cards_an = str(cards_an).strip()

        adv = parsed_dict.get("advice", "")
        if isinstance(adv, list):
            adv = "\n".join(str(a) for a in adv)
        adv = str(adv).strip()

        # Dọn dẹp nếu Gemini vô tình chèn header vào trong các trường con
        conc = re.sub(r"^(?:🎯|[#*_\s])*\s*(?:KẾT LUẬN|TỔNG QUAN)[^:\n]*[:\n]*", "", conc, flags=re.IGNORECASE).strip()
        cards_an = re.sub(r"^(?:🃏|[#*_\s])*\s*(?:Ý NGHĨA CÁC LÁ BÀI|Ý NGHĨA)[^:\n]*[:\n]*", "", cards_an, flags=re.IGNORECASE).strip()
        adv = re.sub(r"^(?:💡|[#*_\s])*\s*(?:LỜI KHUYÊN & ĐỊNH HƯỚNG|LỜI KHUYÊN|ĐỊNH HƯỚNG)[^:\n]*[:\n]*", "", adv, flags=re.IGNORECASE).strip()

        if conc and cards_an:
            # Tái tạo đầy đủ bài đọc chuẩn Markdown với các mục phân tách đẹp mắt
            parts = [
                f"🎯 **KẾT LUẬN & TỔNG QUAN:**\n{conc}",
                f"🃏 **Ý NGHĨA CÁC LÁ BÀI:**\n{cards_an}"
            ]
            if adv:
                parts.append(f"💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**\n{adv}")
            full_reading = "\n\n".join(parts)
        elif len(raw_full) > 50:
            full_reading = raw_full
        else:
            parts = []
            if conc:
                parts.append(f"🎯 **KẾT LUẬN & TỔNG QUAN:**\n{conc}")
            if cards_an:
                parts.append(f"🃏 **Ý NGHĨA CÁC LÁ BÀI:**\n{cards_an}")
            if adv:
                parts.append(f"💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**\n{adv}")
            full_reading = "\n\n".join(parts) if parts else (raw_full or text)
    else:
        # Nếu hoàn toàn không phát hiện cấu trúc JSON -> coi như phản hồi Markdown thông thường
        cleaned = text
        if cleaned.startswith("```json"):
            cleaned = re.sub(r"^```json\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        full_reading = cleaned

    # Bước 5: Dọn dẹp câu chào mở đầu rườm rà nếu có
    full_reading = re.sub(
        r"^(.*?(thân mến|thân yêu|chào mừng|chào bạn|dưới đây là|đây là).*?\n+)+",
        "",
        full_reading,
        flags=re.IGNORECASE
    ).strip()

    # Bước 6: Chặn tuyệt đối rò rỉ mã JSON thô ra giao diện người dùng
    if full_reading.startswith("{") and '"topic_tag"' in full_reading:
        full_reading = re.sub(r'^\s*\{\s*', '', full_reading)
        full_reading = re.sub(r'\s*\}\s*$', '', full_reading)
        full_reading = re.sub(r'"[a-zA-Z_]+":\s*"', '', full_reading)
        full_reading = full_reading.replace('",', '\n\n').replace('\\n', '\n').strip()

    # Bước 7: Chuẩn hóa Markdown, đảm bảo xuống dòng các mục 🎯, 🃏, 💡 và gạch đầu dòng
    full_reading = _clean_and_format_tarot_markdown(full_reading)

    return full_reading, topic_tag, mood_tag, summary_headline


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

    async with AI_SEMAPHORE:
        for model_name in ordered_models:
            # Thử với cấu hình chuẩn có schema, nếu model không hỗ trợ thì fallback cấu hình cơ bản
            configs_to_try = [TAROT_GEN_CONFIG, TAROT_GEN_CONFIG_FALLBACK]

            for gen_config in configs_to_try:
                try:
                    print(f"🔮 [Tarot AI] Thử luận giải quẻ '{spread_name}' bằng model '{model_name}'...", flush=True)
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            client.models.generate_content,
                            model=model_name,
                            contents=prompt,
                            config=gen_config,
                        ),
                        timeout=14.0
                    )
                    if response and response.text:
                        raw_text = response.text.strip()
                        full_reading, topic_tag, mood_tag, summary_headline = parse_tarot_ai_response(raw_text)

                        if full_reading:
                            print(f"✅ [Tarot AI] Thành công luận giải với model '{model_name}' (Tag: {topic_tag} | Mood: {mood_tag}).", flush=True)
                            return full_reading, topic_tag, mood_tag, summary_headline

                except asyncio.TimeoutError:
                    print(f"⏱️ [Tarot AI] Model '{model_name}' phản hồi quá lâu (>14s), chuyển sang model tiếp theo...", flush=True)
                    break  # Chuyển ngay sang model tiếp theo trong cascade
                except Exception as e:
                    err_str = str(e)
                    if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                        print(f"⚠️ [Tarot AI] Model '{model_name}' tạm thời quá tải (503 High Demand), tự động chuyển sang model dự phòng tiếp theo...", flush=True)
                        break
                    elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                        print(f"⚠️ [Tarot AI] Model '{model_name}' chạm giới hạn quota (429 Rate Limit), tự động chuyển sang model dự phòng tiếp theo...", flush=True)
                        break
                    elif "response_schema" in err_str or "schema" in err_str.lower():
                        # Model không hỗ trợ response_schema, thử lại với TAROT_GEN_CONFIG_FALLBACK
                        continue
                    else:
                        print(f"⚠️ [Tarot AI] Model '{model_name}' không khả dụng ({type(e).__name__}: {e}), chuyển sang model tiếp theo...", flush=True)
                        break

    print(f"❌ [Tarot AI] Tất cả các model trong danh sách fallback đều thất bại! Sử dụng bộ luận giải chiêm tinh cổ điển từ điển Tarot...", flush=True)
    fallback_parts = [
        "📖 **BÀI LUẬN GIẢI CHIÊM TINH (TỪ ĐIỂN TAROT CỔ ĐIỂN):**\n"
    ]
    for c in drawn_cards:
        orient_str = "Ngược" if c.is_reversed else "Xuôi"
        kw = c.card.keywords_reversed if c.is_reversed else c.card.keywords_upright
        fallback_parts.append(
            f"**🎴 {c.position_title} — {c.card.name_vi} ({orient_str}):**\n"
            f"• *Từ khóa:* {', '.join(kw)}\n"
            f"• *Ý nghĩa:* {c.card.description}\n"
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
    Hỗ trợ tự động fallback sang các model dự phòng nếu model chính quá tải.
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

    async with AI_SEMAPHORE:
        for model_name in ordered_models:
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        client.models.generate_content,
                        model=model_name,
                        contents=prompt,
                        config=TAROT_FOLLOWUP_CONFIG,
                    ),
                    timeout=12.0
                )
                if response and response.text:
                    clean_ans = response.text.strip()
                    # Dọn dẹp nếu có codeblock bọc ngoài
                    if clean_ans.startswith("```"):
                        clean_ans = re.sub(r"^```[a-zA-Z]*\s*", "", clean_ans)
                        clean_ans = re.sub(r"\s*```$", "", clean_ans).strip()
                    return clean_ans
            except Exception as e:
                err_str = str(e)
                if "503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str.lower():
                    continue
                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    continue
                continue

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
