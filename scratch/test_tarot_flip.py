import asyncio
import pathlib
import sys

# Đảm bảo import được module gốc
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from features.tarot.deck import draw_spread
from features.tarot.renderer import render_spread_to_bytes, _generate_card_back
from features.tarot.manager import TarotManager
from features.tarot.tarot_view import TarotFlipView

output_dir = pathlib.Path("scratch/test_outputs")
output_dir.mkdir(parents=True, exist_ok=True)

def test_card_back():
    print("--- 1. KIỂM TRA VẼ LƯNG BÀI TAROT HUYỀN BÍ ---")
    back_img = _generate_card_back(200, 344)
    back_path = output_dir / "test_card_back.png"
    back_img.save(back_path)
    print(f"✅ Đã render thành công ảnh lưng bài Tarot -> {back_path}")

def test_flip_stages():
    print("\n--- 2. KIỂM TRA CÁC GIAI ĐOẠN LẬT THẺ (0 LÁ -> 1 LÁ -> 3 LÁ) ---")
    drawn_3 = draw_spread("ppf")
    
    # Giai đoạn 1: Úp toàn bộ (0 lá lật)
    buf_0 = render_spread_to_bytes("ppf", drawn_3, revealed_indices=set())
    (output_dir / "test_flip_stage_0.png").write_bytes(buf_0.getvalue())
    print("✅ Giai đoạn 0: Úp toàn bộ 3 lá -> test_flip_stage_0.png")

    # Giai đoạn 2: Lật lá 1 (Quá khứ)
    buf_1 = render_spread_to_bytes("ppf", drawn_3, revealed_indices={0})
    (output_dir / "test_flip_stage_1.png").write_bytes(buf_1.getvalue())
    print("✅ Giai đoạn 1: Lật 1 lá (Lá 1 ngửa, Lá 2 & 3 úp) -> test_flip_stage_1.png")

    # Giai đoạn 3: Lật cả 3 lá
    buf_all = render_spread_to_bytes("ppf", drawn_3, revealed_indices={0, 1, 2})
    (output_dir / "test_flip_stage_all.png").write_bytes(buf_all.getvalue())
    print("✅ Giai đoạn 2: Lật toàn bộ 3 lá -> test_flip_stage_all.png")

async def test_flip_view_structure():
    print("\n--- 3. KIỂM TRA KHỞI TẠO CÁC NÚT BẤM CỦA TAROT FLIP VIEW ---")
    manager = TarotManager()

    # Test view cho 1 lá
    drawn_1 = draw_spread("daily")
    v1 = TarotFlipView(
        author_id=123, author_name="Mike", author_avatar_url=None,
        spread_key="daily", spread_info={"name": "Daily Card"},
        drawn_cards=drawn_1, question=None, ai_task=None, tarot_manager=manager
    )
    print(f"✅ View 1 lá: {len(v1.children)} nút -> {[b.label for b in v1.children]}")
    assert len(v1.children) == 1

    # Test view cho 3 lá
    drawn_3 = draw_spread("choices")
    v3 = TarotFlipView(
        author_id=123, author_name="Mike", author_avatar_url=None,
        spread_key="choices", spread_info={"name": "Two Choices"},
        drawn_cards=drawn_3, question="Hỏi A hay B?", ai_task=None, tarot_manager=manager
    )
    print(f"✅ View 3 lá: {len(v3.children)} nút -> {[b.label for b in v3.children]}")
    assert len(v3.children) == 4  # 3 lá + 1 nút lật tất cả

    # Test view cho 5 lá
    drawn_5 = draw_spread("two_paths")
    v5 = TarotFlipView(
        author_id=123, author_name="Mike", author_avatar_url=None,
        spread_key="two_paths", spread_info={"name": "Two Paths"},
        drawn_cards=drawn_5, question="Phân vân?", ai_task=None, tarot_manager=manager
    )
    print(f"✅ View 5 lá: {len(v5.children)} nút -> {[b.label for b in v5.children]}")
    assert len(v5.children) == 6  # 5 lá + 1 nút lật tất cả

    # Test view cho 10 lá
    drawn_10 = draw_spread("celtic")
    v10 = TarotFlipView(
        author_id=123, author_name="Mike", author_avatar_url=None,
        spread_key="celtic", spread_info={"name": "Celtic Cross"},
        drawn_cards=drawn_10, question="Toàn diện?", ai_task=None, tarot_manager=manager
    )
    print(f"✅ View 10 lá: {len(v10.children)} nút -> {[b.label for b in v10.children]}")
    assert len(v10.children) == 11  # 10 lá + 1 nút lật tất cả

    print("\n🎉 TẤT CẢ CÁC BÀI TEST GAMIFICATION LẬT THẺ ĐỀU THÀNH CÔNG RỰC RỠ!")

async def main():
    test_card_back()
    test_flip_stages()
    await test_flip_view_structure()

if __name__ == "__main__":
    asyncio.run(main())
