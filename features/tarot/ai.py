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
    is_valid: bool = Field(description="True nếu câu hỏi hợp lệ (cho bản thân hoặc mối quan hệ mà người hỏi là người trong cuộc cần lời khuyên). False nếu câu hỏi không hợp lệ (người hỏi không nằm trong những người muốn nhận lời khuyên mà bốc bài hỏi cho người khác / soi mói đời tư, tình cảm, bí mật của người thứ ba B và C).", default=True)
    topic_tag: str = Field(description="Phân loại chủ đề: career, love, finance, health, study, general", default="general")
    mood_tag: str = Field(description="Tag vibe/tâm trạng chủ đạo bằng tiếng Việt", default="Cân bằng & Tĩnh tại")
    summary_headline: str = Field(description="Tiêu đề vibe ngắn dưới 15 từ", default="")
    conclusion: str = Field(description="Kết luận trực diện, đúc kết xu hướng rõ ràng không lấp lửng trong 1-2 câu", default="")
    cards_analysis: str = Field(description="Phân tích chi tiết từng lá bài trong ngữ cảnh câu hỏi", default="")
    story_synthesis: str = Field(description="Dòng chảy câu chuyện xâu chuỗi toàn bộ quẻ bài (bắt buộc cho Celtic Cross và trải bài nhiều lá)", default="")
    decision_matrix: str = Field(description="Tiêu chí chốt hạ rõ ràng (khi nào chọn Có/Làm, khi nào chọn Không/Bỏ, cách chốt tức thì - bắt buộc cho Yes/No và Choices)", default="")
    final_outcome: str = Field(description="Cái kết cuối cùng và đích đến dứt khoát của vấn đề (bắt buộc cho Celtic Cross và trải bài tiến trình)", default="")
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


def extract_question_mentions_context(
    question: Optional[str],
    user_name: str,
    user_id: Optional[int] = None,
    guild: Optional[Any] = None,
    bot_id: Optional[int] = None,
    bot_name: str = "MikeDaBot"
) -> Tuple[str, str]:
    """
    Trích xuất và phân tích đối tượng được tag/nhắc đến trong câu hỏi Tarot:
    - Nhận diện các tag Discord dạng <@123456789> hoặc <@!123456789>.
    - Nhận diện các tag văn bản dạng @Name.
    - Phân biệt rõ:
      1. Người yêu cầu bốc bài (user_name / user_id)
      2. Chính Bot (bot_id / bot_name)
      3. Người thứ hai / Thành viên khác trong server (@Member).
    - Chuẩn hóa câu hỏi: Thay thế <@123456789> thành @DisplayName để Gemini hiểu trực quan.
    - Trả về Tuple: (normalized_question, mentions_context_text)
    """
    if not question:
        return "", ""

    clean_q = question
    raw_mentions = re.findall(r"<@!?(\d+)>", question)
    entities = []
    seen_ids = set()

    # 1. Giải mã các mention Discord nguyên bản <@12345...>
    for uid_str in raw_mentions:
        uid = int(uid_str)
        if uid in seen_ids:
            continue
        seen_ids.add(uid)
        pattern = rf"<@!?{uid}>"

        if bot_id and uid == bot_id:
            tag_name = f"@{bot_name}"
            entities.append({"type": "bot", "name": tag_name, "id": uid, "desc": "Chính Bạn (Tarot Bot / Reader)"})
            clean_q = re.sub(pattern, tag_name, clean_q)
        elif user_id and uid == user_id:
            tag_name = f"@{user_name}"
            entities.append({"type": "self", "name": tag_name, "id": uid, "desc": f"Chính người hỏi ({user_name})"})
            clean_q = re.sub(pattern, tag_name, clean_q)
        else:
            m_name = None
            is_bot = False
            if guild and hasattr(guild, "get_member"):
                member = guild.get_member(uid)
                if member:
                    m_name = member.display_name
                    is_bot = getattr(member, "bot", False)
            if not m_name:
                m_name = f"ThànhViên_{uid}"

            tag_name = f"@{m_name}"
            clean_q = re.sub(pattern, tag_name, clean_q)
            if is_bot or (bot_name and m_name.lower() == bot_name.lower()):
                entities.append({"type": "bot", "name": tag_name, "id": uid, "desc": "Bot trong server"})
            else:
                entities.append({"type": "other", "name": tag_name, "id": uid, "desc": f"Thành viên khác trong server ({tag_name})"})

    # 2. Giải mã các mention văn bản thường @Name
    text_tags = re.findall(r"(?<!\w)@([\w\.\'\-]+)", clean_q)
    for tag in text_tags:
        t_clean = tag.strip()
        t_lower = t_clean.lower()
        if any(e["name"].lstrip("@").lower() == t_lower for e in entities):
            continue

        if t_lower in ["bot", "mikedabot", "mike bot", "mikesbot", "mike_bot"] or (bot_name and t_lower == bot_name.lower()):
            entities.append({"type": "bot", "name": f"@{t_clean}", "id": bot_id, "desc": "Chính Bạn (Tarot Bot / Reader)"})
        elif t_lower == user_name.lower() or (user_id and str(user_id) == t_clean):
            entities.append({"type": "self", "name": f"@{t_clean}", "id": user_id, "desc": f"Chính người hỏi ({user_name})"})
        else:
            is_bot = False
            m_found_name = t_clean
            if guild and hasattr(guild, "members"):
                for m in guild.members:
                    if m.display_name.lower() == t_lower or m.name.lower() == t_lower:
                        m_found_name = m.display_name
                        is_bot = getattr(m, "bot", False) or (bot_id and m.id == bot_id)
                        break
            if is_bot:
                entities.append({"type": "bot", "name": f"@{m_found_name}", "id": None, "desc": "Bot trong server"})
            else:
                entities.append({"type": "other", "name": f"@{m_found_name}", "id": None, "desc": f"Thành viên khác trong server (@{m_found_name})"})

    if not entities:
        return clean_q, "- Phân tích đối tượng: Người hỏi tự hỏi cho chính bản thân mình (không tag đối tượng cụ thể)."

    details = []
    other_members = []
    has_bot = False

    for e in entities:
        if e["type"] == "bot":
            has_bot = True
            details.append(f"  • {e['name']}: Chính Bạn (Tarot Reader / Bot).")
        elif e["type"] == "self":
            details.append(f"  • {e['name']}: Chính người hỏi ({user_name}).")
        else:
            other_members.append(e["name"])
            details.append(f"  • {e['name']}: Thành viên khác trong server (người thật, KHÔNG PHẢI bot).")

    notes = []
    if other_members:
        members_str = ", ".join(other_members)
        notes.append(
            f"  🚨 LƯU Ý VỀ ĐỐI TƯỢNG ĐƯỢC NHẮC ĐẾN: Người hỏi (`{user_name}`) đang hỏi hoặc nhắc đến {members_str} (người thật trong server, không phải bot). "
            f"Nếu đây là câu hỏi vui vẻ, trêu đùa, khen ngợi, hoặc tò mò vô thưởng vô phạt giữa bạn bè (vùng xám/banter), TUYỆT ĐỐI KHÔNG ĐƯỢC QUÁ STRICT MÀ TỪ CHỐI (vẫn là is_valid: true)! "
            f"Hãy dùng năng lượng lá bài để giải mã và đưa ra lời bình luận/nhắn nhủ hóm hỉnh, ấm áp cho {members_str} và `{user_name}`."
        )
    if has_bot:
        notes.append("  💡 LƯU Ý: Người hỏi có nhắc đến Bot. Hãy nhận thức rõ vai trò Reader của bạn và trả lời trực diện.")

    mentions_context_str = (
        "- Phân tích đối tượng được tag/nhắc đến trong câu hỏi:\n"
        + "\n".join(details) + ("\n" + "\n".join(notes) if notes else "")
    )
    return clean_q, mentions_context_str


def _build_tarot_prompt(
    spread_key: str,
    spread_name: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str],
    user_name: str,
    context: Optional[str] = None,
    reader_style: str = "neutral",
    recent_context: Optional[Dict] = None,
    user_id: Optional[int] = None,
    guild: Optional[Any] = None,
    bot_id: Optional[int] = None,
    bot_name: str = "MikeDaBot"
) -> str:
    """Xây dựng prompt AI có trí nhớ bạn cũ, nhận thức @mentions và yêu cầu trả JSON có cấu trúc."""
    clean_question, mentions_info = extract_question_mentions_context(
        question=question,
        user_name=user_name,
        user_id=user_id,
        guild=guild,
        bot_id=bot_id,
        bot_name=bot_name
    )

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
    q_str = f'"{clean_question}"' if clean_question else "Tổng quan năng lượng ngày"

    yes_no_info = ""
    if spread_key == "yes_no" and drawn_cards:
        badge, verdict_desc, _ = get_yes_no_verdict(drawn_cards[0].card, drawn_cards[0].is_reversed)
        yes_no_info = f"\n- Phán Quyết Yes / No Chính Thức Của Quẻ Bài: [{badge}] ({verdict_desc})"

    # Chỉ dẫn văn phong nữ tính đặc thù cho Celeste
    celeste_feminine_guidance = ""
    if reader_style == "healer":
        celeste_feminine_guidance = f"""
    🌸 CHỈ DẪN BẮT BUỘC DÀNH RIÊNG CHO CELESTE (NGƯỜI PHỤ NỮ DỊU DÀNG, NỮ TÍNH & THẤU CẢM):
    - Trò chuyện với `{user_name}` bằng tâm thế của một người phụ nữ vô cùng đằm thắm, dịu dàng, ấm áp và chở che.
    - Xưng hô thân thương và đong đầy tình cảm ('bạn thương', 'người bạn của mình', 'mình cảm nhận được rằng...', 'hãy thả lỏng trái tim nhé...').
    - Lồng ghép những hình ảnh ẩn dụ giàu chất thơ và tính nữ (ánh trăng dịu mát vỗ về bóng đêm, tách trà thơm sau cơn mưa rào, sự nhẫn nại của hạt mầm trong lòng đất, đóa hoa kiên cường nở muộn...).
    - TUYỆT ĐỐI KHÔNG dùng giọng văn trung tính, cộc lốc, khô khan như báo cáo kỹ thuật!
    - Dù dịu dàng vỗ về, Celeste KHÔNG BAO GIỜ nói nước đôi hay lấp lửng: cô ấy mang sự thông tuệ của một người phụ nữ sâu sắc, nhẹ nhàng nhưng dứt khoát cầm tay chỉ lối và trao cho `{user_name}` tiêu chí chọn lựa sáng suốt nhất.
        """.strip()

    # Chỉ dẫn chuyên sâu cho từng kiểu trải bài
    spread_special_instructions = ""
    if spread_key == "yes_no":
        spread_special_instructions = f"""
    ⚡ CHỈ DẪN BẮT BUỘC CHO TRẢI BÀI YES / NO (ĐỊNH HƯỚNG RẼ NHÁNH: NẾU A THÌ VẬY, NẾU B THÌ VẬY):
    - Ngay cả khi lá bài mang tính phân vân / do dự (như 2 Kiếm, 7 Cốc, The Hanged Man, 2 Xu...), TUYỆT ĐỐI TRÁNH buông câu 'tùy bạn tự quyết' mà thiếu định hướng cụ thể!
    - Trong mục `decision_matrix` và bài đọc Markdown, BẮT BUỘC phân tích rõ ràng 2 nhánh quyết định:
      👉 **Nếu bạn chọn CÓ / LÀM (Hướng A):** Phân tích rõ điều kiện thuận lợi, hành động cần làm ngay, và cái giá/sự nỗ lực cần chuẩn bị sẵn sàng.
      👉 **Nếu bạn chọn KHÔNG / BỎ (Hướng B):** Phân tích rõ dấu hiệu cảnh báo, cách dừng lại dứt khoát và sự giải tỏa/bình yên nhận lại để không còn cắn rứt.
      🎯 **Quy tắc chốt hạ dứt khoát (10 giây / 1 phút):** Tiêu chí tự vấn then chốt để `{user_name}` tự tin chốt nhánh đi phù hợp nhất với hoàn cảnh của mình.
        """.strip()
    elif spread_key == "celtic":
        spread_special_instructions = f"""
    🏆 CHỈ DẪN BẮT BUỘC CHO TRẢI BÀI CELTIC CROSS (10 LÁ - BỨC TRANH TOÀN CẢNH & DÒNG CHẢY CÂU CHUYỆN):
    - Trải bài Celtic Cross là trải bài kinh điển 10 lá, TUYỆT ĐỐI KHÔNG được giải qua loa hay chỉ tóm tắt 1 câu ngắn!
    - BẮT BUỘC có đầy đủ 5 mục lớn:
      1. 🎯 **KẾT LUẬN & TỔNG QUAN:** Đúc kết bức tranh toàn cảnh ngắn gọn, sắc bén và có chiều sâu.
      2. 🃏 **Ý NGHĨA CHI TIẾT 10 LÁ BÀI:** Phân tích từng lá theo đúng vị trí của nó (Lá 1: Bản chất thực tại, Lá 2: Trở ngại/Thách thức, Lá 3: Căn nguyên quá khứ, Lá 4: Quá khứ gần, Lá 5: Mục tiêu/Ý thức, Lá 6: Tương lai gần, Lá 7: Tâm thế bản thân, Lá 8: Môi trường ngoại cảnh, Lá 9: Hy vọng & Nỗi sợ, Lá 10: Kết quả cuối cùng).
      3. 📖 **DÒNG CHẢY CÂU CHUYỆN (SỰ KẾT NỐI TOÀN BỘ 10 LÁ):** (Trường `story_synthesis`):
         Xâu chuỗi 10 lá thành một câu chuyện cuộc đời liền mạch, sống động:
         + Trục thực tại & Thách thức (Lá 1 + 2) đối thoại thế nào với cội nguồn và quá khứ gần (Lá 3 + 4)?
         + Mục tiêu lý trí (Lá 5) và tương lai gần (Lá 6) đang hướng người hỏi về đâu?
         + Sự giằng co giữa tâm thế/nỗi sợ bên trong (Lá 7 + 9) với sức ép ngoại cảnh (Lá 8) tạo nên áp lực gì?
      4. 🏆 **CÁI KẾT CUỐI CÙNG & ĐÍCH ĐẾN:** (Trường `final_outcome`):
         Kết lại CỰC KỲ RÕ RÀNG, DỨT KHOÁT, KHÔNG MẬP MỜ! Dựa trên Lá 10 và toàn bộ hành trình để khẳng định: Tình huống sẽ đi về đâu? Cái kết thành bại ra sao? Bước ngoặt lớn nhất cần đón nhận là gì?
      5. 💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG CHIẾN LƯỢC:** Lời khuyên hành động thực tế, thông thái.
        """.strip()
    elif spread_key in ("choices", "two_paths"):
        spread_special_instructions = f"""
    ⚖️ CHỈ DẪN BẮT BUỘC CHO TRẢI BÀI SO SÁNH LỰA CHỌN (CHOICES / TWO PATHS):
    - BẮT BUỘC so sánh đối đầu trực diện trong mục `decision_matrix` và bài đọc:
      + Nếu chọn Phương án A: Được gì, mất gì, con đường sẽ ra sao?
      + Nếu chọn Phương án B: Được gì, mất gì, con đường sẽ ra sao?
      + Lựa chọn cuối cùng là ở bạn, nhưng chỉ rõ phương án nào tối ưu hơn dựa trên năng lượng lá bài để bạn dễ dàng cân nhắc!
        """.strip()
    elif spread_key == "daily":
        spread_special_instructions = f"""
    ⭐ CHỈ DẪN BẮT BUỘC CHO TRẢI BÀI NGÀY (DAILY - CHỐNG NHÀM CHÁN & LẤP LỬNG):
    - Không chỉ nói chung chung 'hôm nay bạn hãy bình tĩnh/vui vẻ'.
    - BẮT BUỘC chỉ rõ trong bài đọc Markdown:
      ⭐ **Điểm sáng năng lượng hôm nay:** Cơ hội hoặc vận may cụ thể nhất trong ngày.
      ⚠️ **Cạm bẫy cần tránh:** 1 hành vi / cảm xúc dễ gây hỏng việc (bốc đồng, trì hoãn, chi tiêu, tranh cãi...).
      ⚡ **Hành động vàng:** 1 việc nên làm ngay hôm nay để ngày trôi qua trọn vẹn nhất.
        """.strip()
    elif spread_key == "ppf":
        spread_special_instructions = f"""
    📖 CHỈ DẪN BẮT BUỘC CHO TRẢI BÀI QUÁ KHỨ - HIỆN TẠI - TƯƠNG LAI (PPF):
    - Trong mục `story_synthesis` và bài đọc, BẮT BUỘC làm rõ mối quan hệ nhân quả: Hành động/bài học trong Quá khứ đã định hình Hiện tại thế nào, và nếu giữ nguyên quán tính này thì Tương lai sẽ dẫn đến đâu.
    - Đưa ra điểm tựa hành động đòn bẩy ở Hiện tại để bẻ lái tương lai sang hướng tốt đẹp nhất.
        """.strip()

    prompt = f"""
    Bạn là Tarot Reader chuyên nghiệp và am tường triết lý 78 lá bài Tarot Rider-Waite.
    Hãy đọc quẻ bài cho `{user_name}` dựa trên đúng ý nghĩa biểu tượng của các lá bài được rút.

    {persona_prompt}

    {celeste_feminine_guidance}

    {memory_prompt}

    THÔNG TIN QUẺ BÀI:
    - Người hỏi: `{user_name}` | Câu hỏi: {q_str}{ctx_str}
    {mentions_info}
    - Kiểu trải bài: {spread_name} ({len(drawn_cards)} lá){yes_no_info}
    - Danh sách lá bài & Ý nghĩa biểu tượng chuẩn:
    {cards_context}

    {spread_special_instructions}

    🚨 NGUYÊN TẮC GIẢI BÀI BẮT BUỘC (QUAN TRỌNG):
    1. ĐÚNG BẢN CHẤT Ý NGHĨA TAROT: Cả 3 Persona (Orion, Celeste, Jester) đều phải giải đúng ý nghĩa nguyên bản của lá bài.
    2. SỰ KHÁC BIỆT Ở PHONG CÁCH DIỄN ĐẠT:
       - Orion: phân tích điềm tĩnh, triết lý, thực tế, dứt khoát và sâu sắc.
       - Celeste: ngọt ngào, dịu dàng, ấm áp, đậm chất nữ tính, chở che nhưng thông tuệ chỉ lối sáng tỏ.
       - Jester: dí dỏm, tếu táo, trào phúng vui tươi, bóc trần sự thật ngầm hiểu sắc bén và thực tế.
    3. ĐỊNH HƯỚNG RẼ NHÁNH RÕ RÀNG ("NẾU LÀ A THÌ NÊN VẬY, CÒN B THÌ NÊN VẬY, LỰA CHỌN LÀ Ở BẠN"):
       - Khi gặp tình huống phân vân / do dự / lưỡng lự (như lá 2 Kiếm, 7 Cốc, The Hanged Man, 2 Xu, hoặc trải Yes/No, Choices):
         + TUYỆT ĐỐI TRÁNH buông câu ba phải lười biếng kiểu 'tùy bạn tự quyết' mà không phân tích cụ thể từng con đường.
         + Thay vào đó, BẮT BUỘC cung cấp BẢN ĐỒ ĐỊNH HƯỚNG 2 CHIỀU:
           • Nếu chọn Hướng A (hoặc bối cảnh A diễn ra): Nên hành động ra sao, đón nhận điều gì, cần chuẩn bị tinh thần cho thách thức nào?
           • Nếu chọn Hướng B (hoặc bối cảnh B diễn ra): Nên xử lý thế nào, đâu là sự bình yên/giải thoát nhận lại, và cần chú ý điều gì?
         + ĐÚC KẾT: Quyền lựa chọn cuối cùng luôn thuộc về `{user_name}`, nhưng bài giải phải vẽ rõ lộ trình cho từng ngã rẽ để người hỏi dù chọn hướng nào cũng có chiến lược vững vàng!
    4. QUY TẮC ĐẠO ĐỨC & RANH GIỚI TRẢI BÀI (NGƯỜI HỎI & NGƯỜI THỨ BA - BẮT BUỘC TUÂN THỦ):
       - BẢN CHẤT CỦA TAROT: Tarot là công cụ soi chiếu nội tâm và trao lời khuyên, định hướng hành động cho CHÍNH người đang bốc bài (`{user_name}`).
       - TRƯỜNG HỢP HỢP LỆ:
         + Người hỏi (`{user_name}`) hỏi về bản thân mình (công việc, học tập, tình cảm, định hướng phát triển cá nhân).
         + VẪN CHO PHÉP hỏi về người khác NẾU `{user_name}` là một bên trong mối quan hệ/tình huống đó và đang tìm kiếm góc nhìn, lời khuyên cho chính bản thân mình.
         + CÂU HỎI VÙNG XÁM / TRÊU ĐÙA / KHEN NGỢI BẠN BÈ: Hoàn toàn hợp lệ (`is_valid: true`). Dùng năng lượng lá bài để nhận xét, tán dương hoặc trêu đùa dí dỏm về người bạn đó.
       - TRƯỜNG HỢP TUYỆT ĐỐI KHÔNG HỢP LỆ (CHỈ TỪ CHỐI KHI CÓ Ý ĐỒ XẤU / SOI MÓI ĐỜI TƯ ĐỘC HẠI):
         + Chỉ từ chối (`is_valid: false`) khi người yêu cầu bốc bài (`{user_name}`) KHÔNG NẰM TRONG NHỮNG NGƯỜI MUỐN NHẬN LỜI KHUYÊN, mà bốc bài để soi mói đời tư, bí mật cá nhân, xu hướng tính dục riêng tư, chuyện tình cảm chia tay/cắm sừng/nợ nần giữa hai người thứ ba B và C mà `{user_name}` không phải là người trong cuộc.
       - HÀNH ĐỘNG KHI CÂU HỎI KHÔNG HỢP LỆ: BẮT BUỘC từ chối khéo léo theo Persona (`is_valid: false`), khuyên `{user_name}` tập trung năng lượng vào cuộc sống và bài học của chính mình.
    5. TRẢ LỜI ĐÚNG TRỌNG TÂM & LÁI THEO LÁ BÀI:
       - Người hỏi hỏi về điều gì thì tập trung giải mã đúng điều đó (công việc, học tập, tài chính, hay tình cảm). Tuyệt đối KHÔNG tự suy diễn mọi câu hỏi thành chuyện tình cảm lứa đôi.
       - Gắn hình ảnh, hành động của lá bài với sự việc cụ thể trong câu hỏi.
       - Lời khuyên phải mang tính hành động cụ thể (Actionable Advice), không sáo rỗng.
    6. ĐỒNG BỘ TUYỆT ĐỐI VỚI PHÁN QUYẾT YES / NO (NẾU LÀ TRẢI BÀI YES/NO):
       - Phán quyết Yes/No và toàn bộ bài giải BẮT BUỘC phải đồng thuận với Phán Quyết Yes / No Chính Thức được nêu ở trên.
    7. PHÂN BIỆT RÕ VAI TRÒ ĐỐI TƯỢNG KHI CÓ TAG (@MENTION) TRONG CÂU HỎI:
       - Phân biệt 3 đối tượng độc lập: Người bốc bài (`{user_name}`), Thành viên khác được tag (@Name), và Chính Bạn (Tarot Reader).

    🚨 YÊU CẦU ĐỊNH DẠNG ĐẦU RA (BẮT BUỘC TRẢ JSON CHUẨN):
    1. `is_valid`: True nếu hợp lệ, False nếu câu hỏi soi mói đời tư người thứ ba độc hại.
    2. `topic_tag`: 1 trong các tag `career`, `love`, `finance`, `health`, `study`, `general`.
    3. `mood_tag`: 1 cụm từ tiếng Việt ngắn gọn mô tả vibe/tâm trạng chủ đạo.
    4. `summary_headline`: 1 câu tóm tắt cực ngắn (dưới 15 từ) đúc kết thông điệp cốt lõi.
    5. `conclusion`: Câu kết luận trực diện, đúc kết xu hướng rõ ràng không lấp lửng trong 1-2 câu.
    6. `cards_analysis`: Phân tích chi tiết từng lá bài trong ngữ cảnh câu hỏi, mỗi lá BẮT BUỘC có gạch đầu dòng '• **Tên lá bài**:' và xuống hàng riêng biệt.
    7. `story_synthesis`: Dòng chảy câu chuyện xâu chuỗi toàn bộ quẻ bài (bắt buộc cho Celtic Cross và trải bài nhiều lá).
    8. `decision_matrix`: Tiêu chí chốt hạ rõ ràng (khi nào chọn Có/Làm, khi nào chọn Không/Bỏ, cách chốt tức thì - bắt buộc cho Yes/No và Choices).
    9. `final_outcome`: Cái kết cuối cùng và đích đến dứt khoát của vấn đề (bắt buộc cho Celtic Cross và trải bài tiến trình).
    10. `advice`: Lời khuyên hành động thực tế, thông thái và khích lệ người hỏi.
    11. `full_reading`: Toàn bộ bài giải hoàn chỉnh dạng Markdown, BẮT BUỘC phân tách các mục rõ ràng bằng 2 dấu xuống dòng (\\n\\n) theo đúng cấu trúc của kiểu trải bài:
       - Với Celtic Cross:
         🎯 **KẾT LUẬN & TỔNG QUAN:**
         🃏 **Ý NGHĨA CHI TIẾT 10 LÁ BÀI:**
         📖 **DÒNG CHẢY CÂU CHUYỆN (SỰ KẾT NỐI TOÀN BỘ TRẢI BÀI):**
         🏆 **CÁI KẾT CUỐI CÙNG & ĐÍCH ĐẾN:**
         💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
       - Với Yes / No:
         🎯 **KẾT LUẬN & TỔNG QUAN:**
         🃏 **Ý NGHĨA CÁC LÁ BÀI:**
         ⚡ **TIÊU CHÍ CHỐT HẠ (KHI NÀO NÊN CHỌN CÁI NÀO):**
         💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
       - Với Choices / Two Paths:
         🎯 **KẾT LUẬN & TỔNG QUAN:**
         🃏 **Ý NGHĨA CÁC LÁ BÀI:**
         ⚖️ **SO SÁNH TRỰC DIỆN & TIÊU CHÍ CHỐT HẠ:**
         💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
       - Với Daily:
         🎯 **KẾT LUẬN & TỔNG QUAN:**
         🃏 **Ý NGHĨA LÁ BÀI:**
         ⭐ **ĐIỂM SÁNG NĂNG LƯỢNG HÔM NAY:**
         ⚠️ **CẠM BẪY CẦN TRÁNH TRONG NGÀY:**
         ⚡ **HÀNH ĐỘNG VÀNG ĐỂ TỐI ƯU MỘT NGÀY:**
         💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
       - Với các trải bài khác (PPF, MBS, Horseshoe, Single):
         🎯 **KẾT LUẬN & TỔNG QUAN:**
         🃏 **Ý NGHĨA CÁC LÁ BÀI:**
         📖 **DÒNG CHẢY CÂU CHUYỆN (TIẾN TRÌNH CHIÊM NGHIỆM):**
         💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**
    """.strip()
    return prompt


def _clean_and_format_tarot_markdown(text: str) -> str:
    """
    Chuẩn hóa cấu trúc Markdown bài giải Tarot:
    - Loại bỏ ký tự thừa hoặc tag in đậm bị treo (dangling **).
    - Chuẩn hóa các đề mục icon chính (🎯, 🃏, 💡, 🔮, ⚡, 📖, 🎭, 💖, ✨, 🏆, ⚖️, ⭐, ⚠️).
    - Giữ nguyên các dấu gạch nối giữa dòng (' - Ngược', 'A - B') và chỉ chuyển đổi gạch đầu dòng.
    """
    if not text:
        return ""

    t = text.strip()

    # 1. Loại bỏ các ký tự đánh dấu heading Markdown (#, ##, ###) ở đầu dòng
    t = re.sub(r"^[ \t]*#+[ \t]*", "", t, flags=re.MULTILINE)

    # 2. Xóa các dòng rác chỉ chứa dấu sao hoặc dấu cách
    t = re.sub(r"^\s*\*+\s*$", "", t, flags=re.MULTILINE)

    icons = "🎯🃏💡🔮⚡📖🎭💖✨🏆⚖️⭐⚠️"

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


def parse_tarot_ai_response(raw_text: str) -> Tuple[str, str, str, str, bool]:
    """
    Phân tích và trích xuất dữ liệu an toàn từ phản hồi của Gemini AI.
    Sử dụng cơ chế đa tầng (Direct JSON -> Regex Fallback -> Text Cleaning)
    đảm bảo 100% không bao giờ làm lộ mã JSON thô ra giao diện người dùng Discord.
    Trả về Tuple: (full_reading_markdown, topic_tag, mood_tag, summary_headline, is_valid)
    """
    if not raw_text:
        return "", "general", "Năng lượng tích cực", "", True

    text = raw_text.strip()

    # Giá trị mặc định
    topic_tag = "general"
    mood_tag = "Năng lượng tích cực"
    summary_headline = ""
    full_reading = ""
    is_valid = True

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
            "story_synthesis",
            "decision_matrix",
            "final_outcome",
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
        # Xử lý is_valid
        raw_is_valid = parsed_dict.get("is_valid", True)
        if isinstance(raw_is_valid, bool):
            is_valid = raw_is_valid
        elif isinstance(raw_is_valid, str):
            is_valid = raw_is_valid.strip().lower() not in ("false", "0", "no", "invalid", "vi_pham")
        else:
            is_valid = True

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

        story_syn = parsed_dict.get("story_synthesis", "")
        if isinstance(story_syn, list):
            story_syn = "\n".join(str(s) for s in story_syn)
        story_syn = str(story_syn).strip()

        dec_mat = parsed_dict.get("decision_matrix", "")
        if isinstance(dec_mat, list):
            dec_mat = "\n".join(str(d) for d in dec_mat)
        dec_mat = str(dec_mat).strip()

        fin_out = parsed_dict.get("final_outcome", "")
        if isinstance(fin_out, list):
            fin_out = "\n".join(str(f) for f in fin_out)
        fin_out = str(fin_out).strip()

        adv = parsed_dict.get("advice", "")
        if isinstance(adv, list):
            adv = "\n".join(str(a) for a in adv)
        adv = str(adv).strip()

        # Dọn dẹp nếu Gemini vô tình chèn header vào trong các trường con
        conc = re.sub(r"^(?:🎯|[#*_\s])*\s*(?:KẾT LUẬN|TỔNG QUAN)[^:\n]*[:\n]*", "", conc, flags=re.IGNORECASE).strip()
        cards_an = re.sub(r"^(?:🃏|[#*_\s])*\s*(?:Ý NGHĨA CÁC LÁ BÀI|Ý NGHĨA CHI TIẾT|Ý NGHĨA)[^:\n]*[:\n]*", "", cards_an, flags=re.IGNORECASE).strip()
        story_syn = re.sub(r"^(?:📖|[#*_\s])*\s*(?:DÒNG CHẢY CÂU CHUYỆN|CÂU CHUYỆN|KẾT NỐI TOÀN BỘ TRẢI BÀI)[^:\n]*[:\n]*", "", story_syn, flags=re.IGNORECASE).strip()
        dec_mat = re.sub(r"^(?:⚡|⚖️|[#*_\s])*\s*(?:TIÊU CHÍ CHỐT HẠ|CHỐT HẠ|SO SÁNH TRỰC DIỆN)[^:\n]*[:\n]*", "", dec_mat, flags=re.IGNORECASE).strip()
        fin_out = re.sub(r"^(?:🏆|[#*_\s])*\s*(?:CÁI KẾT CUỐI CÙNG|ĐÍCH ĐẾN|KẾT QUẢ CUỐI CÙNG)[^:\n]*[:\n]*", "", fin_out, flags=re.IGNORECASE).strip()
        adv = re.sub(r"^(?:💡|[#*_\s])*\s*(?:LỜI KHUYÊN & ĐỊNH HƯỚNG|LỜI KHUYÊN|ĐỊNH HƯỚNG)[^:\n]*[:\n]*", "", adv, flags=re.IGNORECASE).strip()

        # Tái tạo đầy đủ bài đọc chuẩn Markdown với các mục phân tách đẹp mắt
        parts = []
        if conc:
            parts.append(f"🎯 **KẾT LUẬN & TỔNG QUAN:**\n{conc}")
        if cards_an:
            parts.append(f"🃏 **Ý NGHĨA CÁC LÁ BÀI:**\n{cards_an}")
        if story_syn:
            parts.append(f"📖 **DÒNG CHẢY CÂU CHUYỆN (SỰ KẾT NỐI TOÀN BỘ TRẢI BÀI):**\n{story_syn}")
        if dec_mat:
            parts.append(f"⚡ **TIÊU CHÍ CHỐT HẠ (KHI NÀO NÊN CHỌN CÁI NÀO):**\n{dec_mat}")
        if fin_out:
            parts.append(f"🏆 **CÁI KẾT CUỐI CÙNG & ĐÍCH ĐẾN:**\n{fin_out}")
        if adv:
            parts.append(f"💡 **LỜI KHUYÊN & ĐỊNH HƯỚNG:**\n{adv}")

        assembled = "\n\n".join(parts)
        # Nếu raw_full chứa các mục chi tiết và dài hơn hoặc tương đương, ưu tiên raw_full nếu không bị thiếu
        has_rich_sections = any(header in raw_full for header in ["DÒNG CHẢY CÂU CHUYỆN", "TIÊU CHÍ CHỐT HẠ", "CÁI KẾT CUỐI CÙNG", "ĐIỂM SÁNG NĂNG LƯỢNG", "SO SÁNH TRỰC DIỆN"])
        if has_rich_sections and len(raw_full) >= len(assembled):
            full_reading = raw_full
        elif parts:
            full_reading = assembled
        elif len(raw_full) > 50:
            full_reading = raw_full
        else:
            full_reading = text
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

    # Bước 7: Chuẩn hóa Markdown, đảm bảo xuống dòng các mục icon và gạch đầu dòng
    full_reading = _clean_and_format_tarot_markdown(full_reading)

    # Hậu kiểm tra nếu AI đặt tag hoặc nội dung từ chối / vi phạm đạo đức
    check_meta = f"{topic_tag} {mood_tag} {summary_headline}".lower()
    if any(k in check_meta for k in ["ranh giới đạo đức", "từ chối trải bài", "từ chối giải quẻ", "không hợp lệ"]):
        is_valid = False

    return full_reading, topic_tag, mood_tag, summary_headline, is_valid



async def generate_tarot_reading(
    spread_key: str,
    drawn_cards: List[DrawnCard],
    question: Optional[str] = None,
    context: Optional[str] = None,
    reader_style: str = "neutral",
    user_name: str = "Bạn",
    recent_context: Optional[Dict] = None,
    user_id: Optional[int] = None,
    guild: Optional[Any] = None,
    bot_id: Optional[int] = None,
    bot_name: str = "MikeDaBot"
) -> Tuple[str, str, str, str, bool]:
    """
    Gọi AI phân tích quẻ bài với Concurrency Semaphore và Fallback Cascade:
    gemini-3.8-flash ➔ gemini-3.7-flash ➔ gemini-3.6-flash ➔ gemini-3.5-flash ➔ gemini-3.5-flash-lite ➔ gemini-3.1-flash-lite ➔ gemma-4-31b-it.
    Trả về Tuple: (full_reading_markdown, topic_tag, mood_tag, summary_headline, is_valid)
    """
    spread_info = SPREAD_DEFINITIONS.get(spread_key, SPREAD_DEFINITIONS["single"])
    spread_name = spread_info["name"]
    prompt = _build_tarot_prompt(
        spread_key=spread_key,
        spread_name=spread_name,
        drawn_cards=drawn_cards,
        question=question,
        user_name=user_name,
        context=context,
        reader_style=reader_style,
        recent_context=recent_context,
        user_id=user_id,
        guild=guild,
        bot_id=bot_id,
        bot_name=bot_name
    )

    client = get_ai_client()

    models_to_try = getattr(config, "TAROT_FALLBACK_MODELS", [
        config.GEMINI_TAROT_MODEL,
        "gemini-3.8-flash",
        "gemini-3.7-flash",
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

    card_count = len(drawn_cards)
    timeout_duration = 26.0 if card_count >= 5 else 16.0

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
                        timeout=timeout_duration
                    )
                    if response and response.text:
                        raw_text = response.text.strip()
                        full_reading, topic_tag, mood_tag, summary_headline, is_valid = parse_tarot_ai_response(raw_text)

                        if full_reading:
                            print(f"✅ [Tarot AI] Thành công luận giải với model '{model_name}' (Tag: {topic_tag} | Mood: {mood_tag} | Valid: {is_valid}).", flush=True)
                            return full_reading, topic_tag, mood_tag, summary_headline, is_valid

                except asyncio.TimeoutError:
                    print(f"⏱️ [Tarot AI] Model '{model_name}' phản hồi quá lâu (>{timeout_duration}s), chuyển sang model tiếp theo...", flush=True)
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
    return "\n".join(fallback_parts), "general", "Chiêm nghiệm cổ điển", "Thông điệp chiêm tinh cổ điển từ điển Tarot", True


async def generate_followup_answer(
    drawn_cards: List[DrawnCard],
    original_question: Optional[str],
    original_reading: str,
    user_followup_question: str,
    reader_style: str = "neutral",
    user_name: str = "Bạn",
    user_id: Optional[int] = None,
    guild: Optional[Any] = None,
    bot_id: Optional[int] = None,
    bot_name: str = "MikeDaBot"
) -> str:
    """
    Trả lời câu hỏi đào sâu bổ sung của người dùng dựa trên ngữ cảnh quẻ bài vừa giải.
    Hỗ trợ tự động fallback sang các model dự phòng nếu model chính quá tải.
    """
    clean_followup, mentions_context_str = extract_question_mentions_context(
        question=user_followup_question,
        user_name=user_name,
        user_id=user_id,
        guild=guild,
        bot_id=bot_id,
        bot_name=bot_name
    )

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
    "{clean_followup}"
    {mentions_context_str}

    🚨 YÊU CẦU:
    - Trả lời ngắn gọn, trực diện, ấm áp và thấu đáo trong 1-2 đoạn văn (dưới 800 ký tự).
    - Trả lời THẲNG THẮN VÀO TRỌNG TÂM câu hỏi mới, liên kết chặt chẽ với ý nghĩa và chi tiết các lá bài đã xuất hiện. Tuyệt đối không né tránh câu hỏi, không nói chung chung sáo rỗng và không tự áp đặt văn mẫu tình cảm vào các chủ đề khác.
    - NGUYÊN TẮC ĐẠO ĐỨC & RANH GIỚI TRẢI BÀI (BẮT BUỘC TUÂN THỦ):
      + Tarot là công cụ soi chiếu nội tâm cho chính người hỏi `{user_name}`.
      + VẪN CHO PHÉP hỏi về người khác NẾU `{user_name}` là người trong cuộc đang tìm kiếm lời khuyên, hoặc đây là câu hỏi trêu đùa/khen ngợi bạn bè lành mạnh trong server (vùng xám/banter - KHÔNG được quá strict).
      + CHỈ TỪ CHỐI nếu câu hỏi mang tính soi mói đời tư, bí mật độc hại của bên thứ ba mà `{user_name}` không liên quan.
      + Khi câu hỏi không hợp lệ, hãy từ chối trả lời khéo léo theo đúng Persona (Orion nghiêm nghị giữ ranh giới, Celeste dịu dàng nhắc nhở tôn trọng riêng tư, Jester cà khịa tính hóng chuyện thiên hạ) và khuyên `{user_name}` tập trung năng lượng vào bản thân.
    """.strip()

    client = get_ai_client()

    models_to_try = getattr(config, "TAROT_FALLBACK_MODELS", [
        config.GEMINI_TAROT_MODEL,
        "gemini-3.8-flash",
        "gemini-3.7-flash",
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
