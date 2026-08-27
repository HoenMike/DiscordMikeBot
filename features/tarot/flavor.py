"""
features/tarot/flavor.py - Phát hiện các combo bài Tarot hiếm & sinh Flavor Text huyền bí.

Thuần logic Python, không gọi AI ngoài:
- Nhận diện combo toàn Major Arcana, The Fool + The World, trùng lá với hôm qua, bộ nguyên tố áp đảo...
- Sinh lời bình chiêm nghiệm tinh tế ở Embed Footer / Lời nhắn vũ trụ.
"""

from typing import List, Optional
from features.tarot.deck import DrawnCard


def detect_spread_flavor(drawn_cards: List[DrawnCard], previous_daily_card_id: Optional[str] = None) -> Optional[str]:
    """
    Phát hiện các sự kết hợp bài đặc biệt và sinh ra lời bình huyền bí tinh tế.
    Trả về chuỗi Flavor text nếu có, hoặc None nếu là quẻ bài thông thường.
    """
    if not drawn_cards:
        return None

    card_count = len(drawn_cards)
    card_ids = {c.card.id for c in drawn_cards}

    # 1. Combo The Fool (major_00) & The World (major_21)
    if "major_00" in card_ids and "major_21" in card_ids:
        return "🎭 **Chu trình linh hồn viên mãn:** Cả *Kẻ Ngây Thơ (The Fool)* và *Thế Giới (The World)* cùng đồng hiện — dấu hiệu của một chu kỳ cũ khép lại để mở ra hành trình hoàn toàn mới."

    # 2. Toàn bộ Major Arcana (với trải bài từ 3 lá trở lên)
    if card_count >= 3:
        all_major = all(c.card.arcana == "Major" for c in drawn_cards)
        if all_major:
            return "🌌 **Hiện tượng hiếm gặp:** Toàn bộ quẻ bài đều là **Đại Ẩn (Major Arcana)** — Vũ trụ đang dịch chuyển nguồn năng lượng mạnh mẽ cho một bước ngoặt trọng đại của bạn."

    # 3. Trùng lá bài với ngày hôm qua (Daily Easter Egg)
    if previous_daily_card_id and previous_daily_card_id in card_ids:
        matched_card = next((c for c in drawn_cards if c.card.id == previous_daily_card_id), None)
        if matched_card:
            return f"🔄 **Tiếng vọng từ ngày hôm qua:** Lá bài *{matched_card.card.name_vi}* lại một lần nữa tìm đến bạn — dường như vũ trụ đang nhấn mạnh một thông điệp bạn cần chiêm nghiệm sâu sắc hơn."

    # 4. Kiểm tra Nguyên Tố / Bộ Ẩn Phụ áp đảo (Suit Dominance - với trải bài >= 3 lá)
    if card_count >= 3:
        suit_counts = {"Swords": 0, "Cups": 0, "Wands": 0, "Pentacles": 0}
        for c in drawn_cards:
            if c.card.arcana in suit_counts:
                suit_counts[c.card.arcana] += 1

        for suit, count in suit_counts.items():
            # Nếu 1 bộ chiếm >= 3 lá hoặc >= 60% trải bài
            if count >= 3 or (card_count >= 3 and count / card_count >= 0.6):
                if suit == "Swords":
                    return "⚔️ **Nguyên tố Khí áp đảo (Bộ Kiếm):** Tâm trí bạn đang ngập tràn suy nghĩ, đấu tranh lý trí hoặc những quyết định cân não cần sự sáng suốt."
                elif suit == "Cups":
                    return "💖 **Nguyên tố Nước áp đảo (Bộ Cốc):** Cảm xúc, trực giác và những kết nối tâm hồn sâu sắc đang là trọng tâm dẫn dắt năng lượng của bạn."
                elif suit == "Wands":
                    return "🔥 **Nguyên tố Lửa áp đảo (Bộ Gậy):** Nguồn năng lượng hành động, đam mê khám phá và nhiệt huyết sáng tạo đang bùng nổ mạnh mẽ."
                elif suit == "Pentacles":
                    return "🌱 **Nguyên tố Đất áp đảo (Bộ Tiền):** Thực tế cuộc sống, tài chính, sự nghiệp và sự ổn định vật chất đang đòi hỏi sự kiên định."

    # 5. Bộ 4 lá Ace (Tứ đại nguyên tố)
    ace_count = sum(1 for c in drawn_cards if c.card.number == 1 and c.card.arcana != "Major")
    if ace_count >= 3:
        return "⚡ **Tụ hội các Khởi nguyên:** Quẻ bài xuất hiện nhiều lá Ace — bạn đang đứng trước những hạt mầm cơ hội vô cùng dồi dào để bắt đầu lại từ đầu."

    return None
