import unittest

import discord

from features.tarot.reading.recommendation import (
    find_similar_recent_question,
    question_similarity,
    recommend_spread,
)
from features.tarot.tarot_view import TarotLauncherView


class FakeTarotManager:
    def __init__(self, history=None):
        self.history = history or []

    async def get_user_history(self, user_id: int, limit: int = 5):
        return self.history[:limit]

    async def is_user_memory_enabled(self, user_id: int):
        return True


def component(view: TarotLauncherView, custom_id: str):
    return next(
        item for item in view.children
        if getattr(item, "custom_id", None) == custom_id
    )


class TarotV2RecommendationTests(unittest.TestCase):
    def test_deep_comparison_recommends_two_paths(self):
        rec = recommend_spread("Tôi đang phân vân đổi việc hay ở lại công ty hiện tại")
        self.assertEqual(rec.spread_key, "two_paths")

    def test_simple_choice_recommends_choices(self):
        rec = recommend_spread("Tôi nên chọn giữa phương án A hay B?")
        self.assertEqual(rec.spread_key, "choices")

    def test_closed_question_recommends_yes_no(self):
        rec = recommend_spread("Tôi có nên gửi proposal này không?")
        self.assertEqual(rec.spread_key, "yes_no")

    def test_similarity_detects_paraphrased_recent_question(self):
        score = question_similarity(
            "Tôi có nên đổi việc hay ở lại?",
            "Tôi đang phân vân đổi việc, nghỉ hay tiếp tục ở lại công ty",
        )
        self.assertGreaterEqual(score, 0.5)

        match = find_similar_recent_question(
            [{
                "question": "Tôi đang phân vân đổi việc, nghỉ hay tiếp tục ở lại công ty",
                "created_at": "2026-10-03",
                "spread_type": "two_paths",
            }],
            "Tôi có nên đổi việc hay ở lại?",
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["spread_type"], "two_paths")


class TarotV2LauncherTests(unittest.IsolatedAsyncioTestCase):
    async def test_launcher_starts_question_first_without_fake_daily_selection(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
        )
        await view.prepare()

        embed = view.build_launcher_embed()
        self.assertIn("Bạn đang muốn hỏi điều gì?", embed.description)
        self.assertEqual(view.selection_source, "default")
        self.assertIsNone(view.recommended_spread)

        start = component(view, "launcher_btn_start")
        self.assertIsInstance(start, discord.ui.Button)
        self.assertTrue(start.disabled)

        spread_select = component(view, "launcher_spread_select")
        self.assertTrue(all(not option.default for option in spread_select.options))

    async def test_question_generates_recommendation_but_requires_accept_or_override(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
            question="Tôi đang phân vân đổi việc hay ở lại công ty",
        )
        await view.prepare()

        self.assertEqual(view.recommended_spread, "two_paths")
        self.assertEqual(view.selection_source, "default")
        self.assertTrue(component(view, "launcher_btn_start").disabled)
        self.assertFalse(component(view, "launcher_btn_recommend").disabled)

        self.assertTrue(view._use_recommendation())
        view._build_components()

        self.assertEqual(view.selected_spread, "two_paths")
        self.assertEqual(view.selection_source, "recommendation")
        self.assertFalse(component(view, "launcher_btn_start").disabled)
        self.assertTrue(component(view, "launcher_btn_recommend").disabled)
        self.assertIn("đề xuất của Asumi", view.build_launcher_embed().description)

    async def test_manual_daily_remains_available_without_question(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
        )
        view.selected_spread = "daily"
        view.selection_source = "manual"
        view._build_components()

        self.assertTrue(view._can_start())
        self.assertFalse(component(view, "launcher_btn_start").disabled)

    async def test_repeated_question_awareness_respects_memory_preference(self):
        class MemoryOffManager(FakeTarotManager):
            async def is_user_memory_enabled(self, user_id: int):
                return False

        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=MemoryOffManager(history=[{
                "question": "Tôi đang phân vân đổi việc hay ở lại công ty",
                "created_at": "2026-10-03",
                "spread_type": "two_paths",
            }]),
            question="Tôi có nên đổi việc hay ở lại?",
        )
        await view.prepare()

        self.assertIsNone(view.similar_question_hint)
        self.assertFalse(any(
            getattr(item, "custom_id", None) == "launcher_context_mode_select"
            for item in view.children
        ))

    async def test_similar_question_shows_context_mode_control(self):
        manager = FakeTarotManager(history=[{
            "question": "Tôi đang phân vân đổi việc, nghỉ hay tiếp tục ở lại công ty",
            "created_at": "2026-10-03",
            "spread_type": "two_paths",
        }])
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=manager,
            question="Tôi có nên đổi việc hay ở lại?",
        )
        await view.prepare()

        self.assertIsNotNone(view.similar_question_hint)
        self.assertIn("từng hỏi một câu khá gần", view.build_launcher_embed().description)
        context_select = component(view, "launcher_context_mode_select")
        self.assertIsInstance(context_select, discord.ui.Select)
        self.assertEqual(
            {option.value for option in context_select.options},
            {"current", "fresh"},
        )


if __name__ == "__main__":
    unittest.main()
