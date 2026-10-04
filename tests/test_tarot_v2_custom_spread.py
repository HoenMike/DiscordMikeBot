import unittest

import discord

from features.tarot.deck import draw_custom_spread
from features.tarot.reading.custom_spread import validate_custom_spread_payload
from features.tarot.tarot_view import TarotLauncherView


class FakeTarotManager:
    async def get_user_history(self, user_id: int, limit: int = 5):
        return []

    async def is_user_memory_enabled(self, user_id: int):
        return True


def valid_payload(count: int = 4):
    return {
        "title": "Bản đồ quyết định",
        "intent": "Tách tình huống thành các góc nhìn có thể kiểm tra.",
        "reason": "Câu hỏi cần nhìn cả hiện trạng, lực kéo, rủi ro và bước tiếp theo.",
        "positions": [
            {
                "id": f"position_{idx}",
                "title": f"Góc nhìn {idx}",
                "description": f"Điều người hỏi cần xem xét ở góc {idx}.",
            }
            for idx in range(1, count + 1)
        ],
    }


class CustomSpreadValidationTests(unittest.TestCase):
    def test_accepts_three_to_seven_unique_positions(self):
        for count in (3, 4, 5, 6, 7):
            schema = validate_custom_spread_payload(valid_payload(count))
            self.assertIsNotNone(schema)
            self.assertEqual(schema.card_count, count)

    def test_rejects_too_small_or_too_large(self):
        self.assertIsNone(validate_custom_spread_payload(valid_payload(2)))
        self.assertIsNone(validate_custom_spread_payload(valid_payload(8)))

    def test_rejects_duplicate_id_or_title(self):
        payload = valid_payload(3)
        payload["positions"][1]["id"] = payload["positions"][0]["id"]
        self.assertIsNone(validate_custom_spread_payload(payload))

        payload = valid_payload(3)
        payload["positions"][1]["title"] = payload["positions"][0]["title"]
        self.assertIsNone(validate_custom_spread_payload(payload))

    def test_rejects_model_supplied_card_fields(self):
        payload = valid_payload(3)
        payload["positions"][0]["card_id"] = "major_01"
        self.assertIsNone(validate_custom_spread_payload(payload))

    def test_bounds_user_visible_text(self):
        payload = valid_payload(3)
        payload["title"] = "x" * 500
        payload["positions"][0]["description"] = "y" * 500
        schema = validate_custom_spread_payload(payload)
        self.assertEqual(len(schema.title), 72)
        self.assertEqual(len(schema.positions[0].description), 180)


class CustomSpreadDrawTests(unittest.TestCase):
    def test_deck_engine_owns_draw_and_preserves_positions(self):
        schema = validate_custom_spread_payload(valid_payload(5))
        positions = [(p.title, p.description) for p in schema.positions]
        cards = draw_custom_spread(positions, seed=12345, schema_title=schema.title)

        self.assertEqual(len(cards), 5)
        self.assertEqual(len({card.card.id for card in cards}), 5)
        self.assertEqual(cards[0].position_title, "LÁ 1: GÓC NHÌN 1")
        self.assertEqual(cards[0].position_description, schema.positions[0].description)

    def test_same_explicit_seed_is_deterministic(self):
        schema = validate_custom_spread_payload(valid_payload(4))
        positions = [(p.title, p.description) for p in schema.positions]
        first = draw_custom_spread(positions, seed=777)
        second = draw_custom_spread(positions, seed=777)
        self.assertEqual(
            [(c.card.id, c.is_reversed) for c in first],
            [(c.card.id, c.is_reversed) for c in second],
        )


class CustomSpreadLauncherTests(unittest.IsolatedAsyncioTestCase):
    async def test_question_exposes_custom_spread_action(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
            question="Tôi nên sắp xếp lại cách làm project này thế nào?",
        )
        await view.prepare()
        custom = next(
            item for item in view.children
            if getattr(item, "custom_id", "") == "launcher_btn_custom"
        )
        self.assertIsInstance(custom, discord.ui.Button)
        self.assertFalse(custom.disabled)
        view.stop()

    async def test_valid_custom_schema_can_start_without_fixed_definition(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
            question="Tôi nên ưu tiên gì?",
        )
        view.custom_spread_schema = validate_custom_spread_payload(valid_payload(3))
        view.selected_spread = "custom"
        view.selection_source = "custom"
        view._build_components()
        self.assertTrue(view._can_start())
        self.assertIn("Smart Custom Spread", view.build_launcher_embed().description)
        view.stop()


if __name__ == "__main__":
    unittest.main()
