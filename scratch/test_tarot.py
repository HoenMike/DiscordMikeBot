import asyncio
import os
import sys
import pathlib

# Ensure workspace root is in sys.path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from features.tarot.deck import (
    TAROT_DECK,
    SPREAD_DEFINITIONS,
    draw_spread,
    get_yes_no_verdict,
    ensure_card_asset
)
from features.tarot.renderer import render_spread_to_bytes
from features.tarot.manager import TarotManager
from features.tarot.ai import generate_tarot_reading

async def test_deck_integrity():
    print("--- 1. KIỂM TRA TÍNH TOÀN VẸN CỦA BỘ 78 LÁ BÀI ---")
    assert len(TAROT_DECK) == 78, f"Mong đợi 78 lá, thực tế có {len(TAROT_DECK)}"
    major_count = sum(1 for c in TAROT_DECK.values() if c.arcana == "Major")
    wands_count = sum(1 for c in TAROT_DECK.values() if c.arcana == "Wands")
    cups_count = sum(1 for c in TAROT_DECK.values() if c.arcana == "Cups")
    swords_count = sum(1 for c in TAROT_DECK.values() if c.arcana == "Swords")
    pentacles_count = sum(1 for c in TAROT_DECK.values() if c.arcana == "Pentacles")

    print(f"✅ Major Arcana: {major_count}/22 lá")
    print(f"✅ Wands: {wands_count}/14 lá")
    print(f"✅ Cups: {cups_count}/14 lá")
    print(f"✅ Swords: {swords_count}/14 lá")
    print(f"✅ Pentacles: {pentacles_count}/14 lá")

    assert major_count == 22 and wands_count == 14 and cups_count == 14 and swords_count == 14 and pentacles_count == 14

    for card_id, card in TAROT_DECK.items():
        assert card.name_en and card.name_vi, f"Thiếu tên: {card_id}"
        assert card.yes_no_affinity in ["YES", "NO", "MAYBE"], f"Sai affinity: {card_id}"
        assert len(card.keywords_upright) > 0, f"Thiếu keywords upright: {card_id}"
        assert len(card.keywords_reversed) > 0, f"Thiếu keywords reversed: {card_id}"
    print("✅ Toàn bộ 78 lá bài đều có đầy đủ thông tin chuẩn xác!")


async def test_spread_drawing_and_yes_no():
    print("\n--- 2. KIỂM TRA RÚT BÀI & PHÁN QUYẾT YES / NO ---")
    for spread_key, spread_def in SPREAD_DEFINITIONS.items():
        drawn = draw_spread(spread_key)
        assert len(drawn) == spread_def["card_count"], f"Lỗi số lượng lá ở {spread_key}"
        card_ids = [d.card.id for d in drawn]
        assert len(set(card_ids)) == len(card_ids), f"Trùng lá bài ở {spread_key}"
        print(f"✅ Rút thành công spread '{spread_key}' ({len(drawn)} lá không trùng lặp)")

    # Test Yes/No logic
    fool = TAROT_DECK["major_00"]
    badge_u, title_u, col_u = get_yes_no_verdict(fool, False)
    badge_r, title_r, col_r = get_yes_no_verdict(fool, True)
    print(f"✅ The Fool (Xuôi): {badge_u} - {title_u} (Color: {hex(col_u)})")
    print(f"✅ The Fool (Ngược): {badge_r} - {title_r} (Color: {hex(col_r)})")

    tower = TAROT_DECK["major_16"]
    badge_t_u, title_t_u, col_t_u = get_yes_no_verdict(tower, False)
    print(f"✅ The Tower (Xuôi): {badge_t_u} - {title_t_u} (Color: {hex(col_t_u)})")


async def test_pillow_rendering():
    print("\n--- 3. KIỂM TRA ENGINE GHÉP ẢNH PILLOW CANVAS TOÀN BỘ 7 SPREADS ---")
    output_dir = pathlib.Path(__file__).parent / "test_outputs"
    output_dir.mkdir(exist_ok=True)

    all_spreads = ["daily", "yes_no", "single", "choices", "two_paths", "horseshoe", "ppf", "mbs", "celtic"]
    for spread_key in all_spreads:
        drawn = draw_spread(spread_key)
        buf = render_spread_to_bytes(spread_key, drawn)
        img_path = output_dir / f"test_spread_{spread_key}.png"
        img_path.write_bytes(buf.getvalue())
        print(f"✅ Render thành công spread '{spread_key}' ({len(buf.getvalue())} bytes) -> {img_path.name}")


async def test_database_and_cooldown():
    print("\n--- 4. KIỂM TRA SQLITE DATABASE & DAILY COOLDOWN ---")
    manager = TarotManager()
    await manager.init_db()

    import random
    test_user_id = random.randint(100000000, 999999999)
    can_draw_1, _ = await manager.check_daily_cooldown(test_user_id)
    assert can_draw_1 is True, "Lần đầu tiên rút bài phải thành công"

    drawn_daily = draw_spread("daily")
    await manager.record_daily_draw(test_user_id, drawn_daily[0])
    print("✅ Đã ghi nhận lượt bốc Daily Card hôm nay.")

    can_draw_2, last_draw = await manager.check_daily_cooldown(test_user_id)
    assert can_draw_2 is False, "Lần thứ hai trong ngày phải bị chặn cooldown"
    print(f"✅ Daily Cooldown hoạt động chính xác: Chặn bốc lại (Lá đã bốc: {last_draw['name_vi']})")

    # Lưu lịch sử quẻ bài
    await manager.save_tarot_history(
        user_id=test_user_id,
        guild_id=12345,
        channel_id=67890,
        spread_type="choices",
        question="Có nên đầu tư vào dự án mới không?",
        drawn_cards=drawn_daily,
        ai_reading="Đây là bài luận giải thử nghiệm."
    )
    history = await manager.get_user_history(test_user_id, limit=5)
    assert len(history) >= 1, "Lịch sử phải có ít nhất 1 bản ghi"
    print(f"✅ Lịch sử quẻ bài lưu thành công: {history[0]['question']}")
    await manager.close()


async def main():
    await test_deck_integrity()
    await test_spread_drawing_and_yes_no()
    await test_pillow_rendering()
    await test_database_and_cooldown()
    print("\n🎉 TOÀN BỘ CÁC BÀI KIỂM THỬ ĐÃ VƯỢT QUA THÀNH CÔNG RỰC RỠ!")

if __name__ == "__main__":
    asyncio.run(main())
