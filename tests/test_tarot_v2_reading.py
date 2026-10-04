import json
import unittest
from unittest.mock import AsyncMock, patch

from features.tarot.ai import (
    _build_tarot_prompt,
    _infer_auto_tone,
    generate_tarot_reading,
    generate_tarot_reading_result,
    generate_why_explanation,
    parse_tarot_ai_response,
    parse_tarot_ai_response_v2,
    recommend_spread_for_question,
)
from features.tarot.deck import DrawnCard, TAROT_DECK
from features.tarot.reading.schema import TarotAIResponseSchema


def drawn(card_id: str, position_index: int, position_title: str, reversed_: bool = False) -> DrawnCard:
    return DrawnCard(
        card=TAROT_DECK[card_id],
        is_reversed=reversed_,
        position_index=position_index,
        position_title=position_title,
        position_description=position_title,
    )


class TarotV2PromptTests(unittest.TestCase):
    def test_prompt_is_connection_first_and_exposes_stable_ids(self):
        cards = [
            drawn("major_02", 0, "Hiện tại"),
            drawn("major_18", 1, "Tương lai", reversed_=True),
        ]
        prompt = _build_tarot_prompt(
            "ppf",
            "Past - Present - Future",
            cards,
            "Tôi có nên quyết định ngay không?",
            "Mai",
            context="Tôi vẫn đang thiếu thông tin từ phía công việc.",
            reader_style="auto",
            recent_context={
                "topic_tag": "career",
                "mood_tag": "Phân vân",
                "last_card_name": "Ẩn Sĩ (Xuôi)",
            },
        )

        self.assertIn("OBSERVE", prompt)
        self.assertIn("CONNECT", prompt)
        self.assertIn("UNCERTAINTY", prompt)
        self.assertIn("card_id=major_02", prompt)
        self.assertIn("card_id=major_18", prompt)
        self.assertIn("position_id=0", prompt)
        self.assertIn("Không cấu trúc bài theo kiểu", prompt)
        self.assertIn("THAM KHẢO NHẸ", prompt)
        self.assertIn("dữ kiện còn thiếu", prompt)

    def test_auto_tone_changes_with_question_type(self):
        self.assertIn("trade-off", _infer_auto_tone("Tôi có nên đổi việc hay ở lại?"))
        self.assertIn("Ấm nhưng trực diện", _infer_auto_tone("Tôi vừa chia tay người yêu"))
        self.assertIn("không đùa", _infer_auto_tone("Tôi đang hỏi về thuốc và bệnh"))


class TarotV2SchemaTests(unittest.TestCase):
    def test_v2_schema_parses_into_current_discord_markdown(self):
        payload = {
            "is_valid": True,
            "topic_tag": "career",
            "mood_tag": "Đang cân nhắc",
            "headline": "Chưa phải lúc khóa quyết định",
            "core_message": "Bạn đang cố chọn khi dữ kiện hai phía chưa cân nhau. Quẻ nghiêng về việc làm rõ thông tin trước khi chốt.",
            "card_insights": [
                {
                    "position_id": "0",
                    "card_id": "major_02",
                    "card_name": "Nữ Tư Tế",
                    "insight": "Hiện tại cần quan sát nhiều hơn là ép câu trả lời.",
                }
            ],
            "connections": [
                {
                    "card_ids": ["major_02", "major_18"],
                    "meaning": "Nữ Tư Tế và Mặt Trăng cùng nhấn mạnh phần thông tin chưa lộ rõ, nhưng theo hai kiểu khác nhau.",
                }
            ],
            "dominant_theme": "Điểm chính của quẻ là chất lượng thông tin, không phải thiếu lựa chọn.",
            "key_card": {
                "card_id": "major_02",
                "card_name": "Nữ Tư Tế",
                "reason": "Nó đặt trọng tâm vào quan sát và chưa vội kết luận.",
            },
            "practical_takeaway": [
                "Xác định thông tin nào còn thiếu trước khi quyết định.",
                "Đặt một mốc thời gian cụ thể để đánh giá lại.",
            ],
            "uncertainty": "Quẻ không thể biết dữ kiện mới sẽ xuất hiện khi nào hoặc quyết định cuối cùng của bạn.",
            "suggested_clarifier_targets": [
                {"position_id": "1", "reason": "Tương lai còn nhiều yếu tố chưa rõ."}
            ],
            "journey_tags": ["decision", "career", "clarity"],
            "refusal_message": "",
        }

        raw = json.dumps(payload, ensure_ascii=False)
        result = parse_tarot_ai_response_v2(raw)

        self.assertTrue(result.is_valid)
        self.assertEqual(result.headline, "Chưa phải lúc khóa quyết định")
        self.assertEqual(result.topic_tag, "career")
        self.assertEqual(result.key_card.card_id, "major_02")
        self.assertEqual(result.journey_tags, ["decision", "career", "clarity"])
        self.assertIn("CỐT LÕI CỦA QUẺ", result.full_reading)
        self.assertIn("CÂU CHUYỆN GIỮA CÁC LÁ", result.full_reading)
        self.assertIn("ĐIỀU ĐÁNG LÀM LÚC NÀY", result.full_reading)
        self.assertIn("ĐIỀU QUẺ CHƯA THỂ NÓI CHẮC", result.full_reading)
        self.assertIn("LÁ CHỦ ĐẠO", result.full_reading)
        self.assertNotIn('"core_message"', result.full_reading)

        legacy_tuple = parse_tarot_ai_response(raw)
        self.assertEqual(legacy_tuple[1], "career")
        self.assertEqual(legacy_tuple[3], "Chưa phải lúc khóa quyết định")

    def test_invalid_v2_response_prefers_refusal_message(self):
        raw = json.dumps({
            "is_valid": False,
            "topic_tag": "general",
            "mood_tag": "Ranh giới",
            "headline": "",
            "core_message": "",
            "card_insights": [],
            "connections": [],
            "dominant_theme": "",
            "key_card": {"card_id": "", "card_name": "", "reason": ""},
            "practical_takeaway": [],
            "uncertainty": "",
            "suggested_clarifier_targets": [],
            "journey_tags": [],
            "refusal_message": "Mình không nên dùng Tarot để soi bí mật riêng tư của người không liên quan đến bạn.",
        }, ensure_ascii=False)

        result = parse_tarot_ai_response_v2(raw)
        self.assertFalse(result.is_valid)
        self.assertEqual(
            result.full_reading,
            "Mình không nên dùng Tarot để soi bí mật riêng tư của người không liên quan đến bạn.",
        )

    def test_legacy_json_is_still_supported(self):
        raw = json.dumps({
            "is_valid": True,
            "topic_tag": "study",
            "mood_tag": "Tập trung",
            "summary_headline": "Đừng học dàn trải",
            "conclusion": "Vấn đề nằm ở việc chia năng lượng quá mỏng.",
            "cards_analysis": "Hai lá cùng kéo về nhu cầu ưu tiên.",
            "advice": "Chọn một mục tiêu học chính cho tuần này.",
            "full_reading": "",
        }, ensure_ascii=False)

        result = parse_tarot_ai_response_v2(raw)
        self.assertEqual(result.headline, "Đừng học dàn trải")
        self.assertIn("CỐT LÕI CỦA QUẺ", result.full_reading)
        self.assertIn("Chọn một mục tiêu học chính", result.full_reading)

    def test_schema_accepts_structured_relationships(self):
        schema = TarotAIResponseSchema(
            headline="Một nhịp chậm có ích",
            connections=[{
                "card_ids": ["major_02", "major_18"],
                "meaning": "Hai lá cùng nhấn mạnh điều chưa rõ.",
            }],
            practical_takeaway=["Kiểm tra dữ kiện còn thiếu."],
            uncertainty="Chưa thể biết kết quả cuối.",
        )
        self.assertEqual(schema.connections[0].card_ids, ["major_02", "major_18"])


class TarotV2RecommendationTests(unittest.TestCase):
    def test_broad_question_uses_real_celtic_key(self):
        spread_key, _, _ = recommend_spread_for_question(
            "Cho tôi bức tranh toàn cảnh về sự nghiệp dài hạn"
        )
        self.assertEqual(spread_key, "celtic")


class TarotV2GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rich_result_and_legacy_adapter_share_same_reading(self):
        cards = [drawn("major_02", 0, "Lời khuyên")]
        payload = json.dumps({
            "is_valid": True,
            "topic_tag": "decision",
            "mood_tag": "Chậm lại",
            "headline": "Đừng ép câu trả lời",
            "core_message": "Thông tin chưa đủ rõ để chốt ngay.",
            "card_insights": [{
                "position_id": "0",
                "card_id": "major_02",
                "card_name": "Nữ Tư Tế",
                "insight": "Quan sát thêm trước khi hành động.",
            }],
            "connections": [],
            "dominant_theme": "Khoảng dừng có ích hơn một quyết định vội.",
            "key_card": {
                "card_id": "major_02",
                "card_name": "Nữ Tư Tế",
                "reason": "Đây là lá duy nhất và trực tiếp nhấn mạnh việc quan sát.",
            },
            "practical_takeaway": ["Xác định một dữ kiện còn thiếu."],
            "uncertainty": "Tarot không thể biết dữ kiện đó sẽ xuất hiện khi nào.",
            "suggested_clarifier_targets": [],
            "journey_tags": ["decision"],
            "refusal_message": "",
        }, ensure_ascii=False)
        response = type("Response", (), {"text": payload})()

        with patch("features.tarot.ai.bounded_ai_generate", new=AsyncMock(return_value=response)):
            rich = await generate_tarot_reading_result(
                "single",
                cards,
                question="Tôi có nên chốt ngay không?",
                user_name="Mai",
            )

        self.assertEqual(rich.headline, "Đừng ép câu trả lời")
        self.assertEqual(rich.key_card.card_id, "major_02")
        self.assertIn("Khoảng dừng có ích", rich.full_reading)

        with patch("features.tarot.ai.generate_tarot_reading_result", new=AsyncMock(return_value=rich)):
            legacy = await generate_tarot_reading(
                "single",
                cards,
                question="Tôi có nên chốt ngay không?",
                user_name="Mai",
            )
        self.assertEqual(legacy, rich.as_legacy_tuple())


class TarotV2WhyTests(unittest.IsolatedAsyncioTestCase):
    async def test_why_fallback_uses_visible_cards_only(self):
        cards = [
            drawn("major_02", 0, "Hiện tại"),
            drawn("major_18", 1, "Tương lai"),
        ]
        with patch("features.tarot.ai.bounded_ai_generate", new=AsyncMock(side_effect=RuntimeError("offline"))):
            answer = await generate_why_explanation(
                cards,
                "Tôi có nên quyết định ngay không?",
                "Quẻ nghiêng về việc chờ thêm dữ kiện.",
                reader_style="auto",
                user_name="Mai",
            )

        self.assertIn("Nữ Tư Tế", answer)
        self.assertIn("Hiện tại", answer)
        self.assertIn("hoàn cảnh thực tế", answer)


if __name__ == "__main__":
    unittest.main()
