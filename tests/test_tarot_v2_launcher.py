import unittest
from unittest.mock import AsyncMock

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


class LauncherCooldownManager(FakeTarotManager):
    def __init__(self, *, daily_available=True, command_available=True):
        super().__init__()
        self.daily_available = daily_available
        self.command_available = command_available

    async def check_daily_cooldown(self, user_id: int):
        if self.daily_available:
            return True, None
        return False, {
            "name_vi": "Mặt Trời",
            "name_en": "The Sun",
            "is_reversed": False,
            "drawn_at": "08:00",
        }

    def check_user_cooldown(self, user_id: int, cooldown_seconds: int):
        return (True, 0) if self.command_available else (False, 12)


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.modals = []

    async def send_message(self, *args, **kwargs):
        self.messages.append((args, kwargs))

    async def send_modal(self, modal):
        self.modals.append(modal)


class FakeInteraction:
    def __init__(self, user_id: int = 1):
        self.user = type("User", (), {"id": user_id})()
        self.response = FakeResponse()


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
    async def test_launcher_prioritizes_question_and_one_tap_daily(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
        )
        await view.prepare()

        embed = view.build_launcher_embed()
        self.assertIn("Bạn muốn xem gì hôm nay?", embed.description)
        self.assertIn("Daily hôm nay", embed.description)
        self.assertEqual(view.selection_source, "default")
        self.assertIsNone(view.recommended_spread)

        question = component(view, "launcher_btn_question")
        daily = component(view, "launcher_btn_daily")
        spread_select = component(view, "launcher_spread_select")
        reader_select = component(view, "launcher_reader_select")

        self.assertEqual(question.row, 0)
        self.assertEqual(daily.row, 0)
        self.assertEqual(daily.label, "☀️ Daily hôm nay")
        self.assertEqual(spread_select.row, 1)
        self.assertEqual(reader_select.row, 2)
        self.assertIn("Tuỳ chọn nâng cao", spread_select.placeholder)
        self.assertTrue(all(not option.default for option in spread_select.options))
        self.assertFalse(any(
            getattr(item, "custom_id", None) == "launcher_btn_start"
            for item in view.children
        ))

    async def test_question_generates_one_click_recommendation_cta(self):
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

        recommend = component(view, "launcher_btn_recommend")
        custom = component(view, "launcher_btn_custom")
        spread_select = component(view, "launcher_spread_select")
        reader_select = component(view, "launcher_reader_select")

        self.assertEqual(recommend.label, "✨ Trải theo đề xuất")
        self.assertEqual(recommend.row, 1)
        self.assertEqual(custom.row, 1)
        self.assertEqual(spread_select.row, 2)
        self.assertEqual(reader_select.row, 3)
        self.assertNotIn("launcher_btn_daily", {
            getattr(item, "custom_id", None) for item in view.children
        })
        self.assertFalse(any(
            getattr(item, "custom_id", None) == "launcher_btn_start"
            for item in view.children
        ))
        self.assertIn("Trải theo đề xuất", view.build_launcher_embed().description)

        self.assertTrue(view._use_recommendation())
        self.assertEqual(view.selected_spread, "two_paths")
        self.assertEqual(view.selection_source, "recommendation")
        self.assertTrue(view._can_start())

    async def test_manual_daily_remains_available_without_question(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
        )
        self.assertIsInstance(component(view, "launcher_btn_daily"), discord.ui.Button)

        view.selected_spread = "daily"
        view.selection_source = "manual"
        view._build_components()

        self.assertTrue(view._can_start())
        start = component(view, "launcher_btn_start")
        self.assertFalse(start.disabled)
        self.assertEqual(start.row, 0)

    async def test_manual_override_stays_secondary_but_can_start(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=FakeTarotManager(),
            question="Tôi nên ưu tiên việc gì tuần này?",
        )
        await view.prepare()
        view.selected_spread = "single"
        view.selection_source = "manual"
        view._build_components()

        start = component(view, "launcher_btn_start")
        spread_select = component(view, "launcher_spread_select")
        self.assertFalse(start.disabled)
        self.assertEqual(start.row, 1)
        self.assertEqual(spread_select.row, 2)

    async def test_daily_quick_path_starts_in_one_click(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=LauncherCooldownManager(),
        )
        await view.prepare()
        view.start_reading = AsyncMock()
        interaction = FakeInteraction()

        await view._handle_daily_button(interaction)

        self.assertEqual(view.selected_spread, "daily")
        self.assertEqual(view.selection_source, "manual")
        view.start_reading.assert_awaited_once_with(interaction)

    async def test_daily_quick_path_rolls_back_when_already_drawn(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=LauncherCooldownManager(daily_available=False),
        )
        await view.prepare()
        interaction = FakeInteraction()

        await view._handle_daily_button(interaction)

        self.assertEqual(view.selection_source, "default")
        self.assertEqual(view.selected_spread, "daily")
        self.assertTrue(interaction.response.messages)
        self.assertIsInstance(component(view, "launcher_btn_daily"), discord.ui.Button)

    async def test_recommendation_rolls_back_when_command_cooldown_blocks_start(self):
        view = TarotLauncherView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            tarot_manager=LauncherCooldownManager(command_available=False),
            question="Tôi đang phân vân đổi việc hay ở lại công ty",
        )
        await view.prepare()
        interaction = FakeInteraction()

        await view._handle_recommendation_button(interaction)

        self.assertEqual(view.selection_source, "default")
        self.assertEqual(view.selected_spread, "daily")
        self.assertTrue(interaction.response.messages)
        self.assertEqual(component(view, "launcher_btn_recommend").label, "✨ Trải theo đề xuất")

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
