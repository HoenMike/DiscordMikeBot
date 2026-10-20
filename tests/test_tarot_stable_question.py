"""Question consistency: same question means stable cards and reusable reading."""
import unittest
from datetime import datetime as real_datetime
from unittest.mock import AsyncMock, patch

from features.tarot import deck
from features.tarot.deck import draw_spread, draw_custom_spread
from features.tarot.reading.reuse import history_question, reuse_or_generate
from features.tarot.reading.schema import TarotReadingResult


class FrozenDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, 9, 0, tzinfo=tz)


class LaterDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 20, 18, 0, tzinfo=tz)


class TomorrowDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 21, 9, 0, tzinfo=tz)


def signature(cards):
    return [(c.card.id, c.is_reversed) for c in cards]


class StableQuestionTests(unittest.TestCase):
    def test_same_user_question_is_stable_across_hours_and_fatigue(self):
        with patch.object(deck, "datetime", FrozenDatetime):
            morning = draw_spread("ppf", user_id=9, question="Khi nào có người yêu?")
        with patch.object(deck, "datetime", LaterDatetime):
            evening = draw_spread(
                "ppf", user_id=9, question="khi nào có người yêu ?",
                fatigue_card_ids=[card.card.id for card in morning],
            )
        self.assertEqual(signature(morning), signature(evening))

    def test_new_day_gets_new_seed_but_explicit_seed_overrides(self):
        with patch.object(deck, "datetime", FrozenDatetime):
            today_seed = deck.compute_tarot_seed(9, "ppf", "Có ny không?")
            cards_a = draw_spread("ppf", seed=123)
        with patch.object(deck, "datetime", TomorrowDatetime):
            tomorrow_seed = deck.compute_tarot_seed(9, "ppf", "Có ny không?")
            cards_b = draw_spread("ppf", seed=123, fatigue_card_ids=[c.card.id for c in cards_a])
        self.assertNotEqual(today_seed, tomorrow_seed)
        self.assertEqual(signature(cards_a), signature(cards_b))

    def test_custom_spread_seed_ignores_recent_cards(self):
        positions = [("A", "Quá khứ"), ("B", "Hiện tại"), ("C", "Tương lai")]
        first = draw_custom_spread(positions, user_id=9, question="Cùng câu hỏi")
        second = draw_custom_spread(
            positions, user_id=9, question="Cùng câu hỏi",
            fatigue_card_ids=[c.card.id for c in first],
        )
        self.assertEqual(signature(first), signature(second))


class ReuseReadingTests(unittest.IsolatedAsyncioTestCase):
    async def test_matching_reading_skips_gemini(self):
        manager = type("Manager", (), {})()
        manager.find_same_day_reading = AsyncMock(return_value={
            "ai_reading": "💬 **TRẢ LỜI NGẮN:** Quẻ chưa hẹn ngày.",
            "topic_tag": "love", "mood_tag": "Tự nhiên",
        })
        generate = AsyncMock()
        result = await reuse_or_generate(
            manager, user_id=9, guild_id=10, channel_id=11,
            spread_key="ppf", question="Khi nào có ny?", context="Đang độc thân",
            drawn_cards=[], reader_style="auto", fresh=False, generate=generate,
        )
        self.assertEqual(result.ai_model, "cached_history")
        self.assertIn("chưa hẹn ngày", result.full_reading)
        generate.assert_not_awaited()
        self.assertEqual(
            manager.find_same_day_reading.await_args.kwargs["question"],
            "Khi nào có ny? (Bối cảnh: Đang độc thân)",
        )

    async def test_cache_failure_generates_instead_of_aborting(self):
        manager = type("Manager", (), {})()
        manager.find_same_day_reading = AsyncMock(side_effect=RuntimeError("DB unavailable"))
        fallback = TarotReadingResult(full_reading="AI newly generated")
        generate = AsyncMock(return_value=fallback)
        result = await reuse_or_generate(
            manager, user_id=9, guild_id=10, channel_id=11,
            spread_key="ppf", question="Q", context=None,
            drawn_cards=[], reader_style="auto", fresh=False, generate=generate,
        )
        self.assertIs(result, fallback)
        generate.assert_awaited_once()

    async def test_new_shuffle_and_manual_style_always_regenerate(self):
        manager = type("Manager", (), {})()
        manager.find_same_day_reading = AsyncMock()
        fresh_result = TarotReadingResult(full_reading="New reading")
        generate = AsyncMock(return_value=fresh_result)
        for new_draw, reader in [(True, "auto"), (False, "chaos")]:
            with self.subTest(new_draw=new_draw, reader=reader):
                result = await reuse_or_generate(
                    manager, user_id=9, guild_id=10, channel_id=11,
                    spread_key="ppf", question="Q", context=None,
                    drawn_cards=[], reader_style=reader, fresh=new_draw,
                    generate=generate,
                )
                self.assertIs(result, fresh_result)
        manager.find_same_day_reading.assert_not_awaited()
        self.assertEqual(generate.await_count, 2)


if __name__ == "__main__":
    unittest.main()
