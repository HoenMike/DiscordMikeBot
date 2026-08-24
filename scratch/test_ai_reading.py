import asyncio
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import config
from features.tarot.deck import draw_spread
from features.tarot.ai import generate_tarot_reading

async def test_live_readings():
    print("==================================================")
    print("🔮 BẮT ĐẦU TEST KÉO API AI THỰC TẾ CHO TRẢI BÀI TAROT 🔮")
    print(f"Cấu hình model Tarot: {config.GEMINI_TAROT_MODEL}")
    print(f"Danh sách Fallback: {config.TAROT_FALLBACK_MODELS}")
    print("==================================================\n")

    test_cases = [
        ("yes_no", "Tôi có nên đổi công việc mới trong tháng này không?", "Hoàng Mai"),
        ("two_paths", "Nên khởi nghiệp mở quán cà phê (A) hay tiếp tục làm lập trình viên (B)?", "Hoàng Mai"),
        ("celtic", "Định hướng phát triển sự nghiệp và cuộc sống trong 6 tháng tới?", "Hoàng Mai"),
    ]

    for spread_key, question, user_name in test_cases:
        print(f"\n--- TEST SPREAD: '{spread_key.upper()}' ---")
        print(f"Câu hỏi: \"{question}\"")
        drawn = draw_spread(spread_key)
        print(f"Số lá rút được: {len(drawn)} lá:")
        for d in drawn:
            orient = "Ngược" if d.is_reversed else "Xuôi"
            print(f"  • [{d.position_title}]: {d.card.name_vi} ({d.card.name_en}) - [{orient}]")

        print("\n⏳ Đang gọi AI luận giải...")
        start_t = asyncio.get_event_loop().time()
        reading_text = await generate_tarot_reading(
            spread_key=spread_key,
            drawn_cards=drawn,
            question=question,
            user_name=user_name
        )
        elapsed = asyncio.get_event_loop().time() - start_t
        print(f"⏱️ Thời gian phản hồi: {elapsed:.2f}s | Độ dài output: {len(reading_text)} ký tự")
        print("📄 OUTPUT TRẢ VỀ TỪ AI:")
        print("--------------------------------------------------")
        print(reading_text)
        print("--------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(test_live_readings())
