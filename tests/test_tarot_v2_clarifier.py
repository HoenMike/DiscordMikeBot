import asyncio
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from PIL import Image

from features.tarot.ai import generate_clarifier_interpretation
from features.tarot.deck import DrawnCard, TAROT_DECK, draw_clarifier
from features.tarot.reading.clarifier import resolve_clarifier_suggestions, target_insight
from features.tarot.reading.schema import (
    TarotCardInsight,
    TarotClarifierResult,
    TarotClarifierTarget,
    TarotReadingResult,
)
from features.tarot.renderer import render_clarifier_board_to_bytes
from features.tarot.rendering.state import ClarifierBoardState
from features.tarot.tarot_view import TarotClarifierTargetView, TarotResultActionView


def drawn(card_id: str, position_index: int, title: str, reversed_: bool = False) -> DrawnCard:
    return DrawnCard(
        card=TAROT_DECK[card_id],
        is_reversed=reversed_,
        position_index=position_index,
        position_title=title,
        position_description=title,
    )


class ClarifierDrawTests(unittest.TestCase):
    def setUp(self):
        self.original = [
            drawn("major_02", 1, "LÁ 1: QUÁ KHỨ"),
            drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True),
            drawn("major_19", 3, "LÁ 3: TƯƠNG LAI"),
        ]

    def test_draw_is_deterministic_and_never_reuses_original_card(self):
        first = draw_clarifier(
            self.original,
            target_position_index=1,
            user_id=123,
            question="Tôi nên làm gì tiếp theo?",
        )
        second = draw_clarifier(
            self.original,
            target_position_index=1,
            user_id=123,
            question="Tôi nên làm gì tiếp theo?",
        )

        self.assertEqual(first.card.id, second.card.id)
        self.assertEqual(first.is_reversed, second.is_reversed)
        self.assertNotIn(first.card.id, {card.card.id for card in self.original})
        self.assertEqual(first.position_index, 4)
        self.assertIn("LÀM RÕ", first.position_title)

    def test_invalid_target_does_not_mutate_original_spread(self):
        before = [(c.card.id, c.is_reversed) for c in self.original]
        with self.assertRaises(ValueError):
            draw_clarifier(self.original, 99, seed=1)
        self.assertEqual(before, [(c.card.id, c.is_reversed) for c in self.original])


class ClarifierTargetTests(unittest.TestCase):
    def setUp(self):
        self.cards = [
            drawn("major_02", 1, "LÁ 1: QUÁ KHỨ"),
            drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True),
            drawn("major_19", 3, "LÁ 3: TƯƠNG LAI"),
        ]

    def test_ai_suggestion_maps_to_real_position_and_insight(self):
        result = TarotReadingResult(
            suggested_clarifier_targets=[
                TarotClarifierTarget(position_id="2", reason="Hiện tại còn mơ hồ.")
            ],
            card_insights=[
                TarotCardInsight(
                    position_id="2",
                    card_id="major_18",
                    card_name="Mặt Trăng",
                    insight="Dữ kiện hiện tại chưa đủ rõ.",
                )
            ],
        )
        suggestions = resolve_clarifier_suggestions(result, self.cards)
        self.assertEqual(suggestions, {1: "Hiện tại còn mơ hồ."})
        self.assertEqual(target_insight(result, self.cards[1]), "Dữ kiện hiện tại chưa đủ rõ.")


class ClarifierAITests(unittest.IsolatedAsyncioTestCase):
    async def test_ai_failure_returns_visible_evidence_fallback(self):
        target = drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True)
        clarifier = drawn("major_09", 4, "LÀM RÕ: HIỆN TẠI")
        with patch(
            "features.tarot.ai.bounded_ai_generate",
            new=AsyncMock(side_effect=RuntimeError("offline")),
        ):
            result = await generate_clarifier_interpretation(
                spread_key="ppf",
                original_question="Tôi có nên quyết định ngay không?",
                context="Tôi vẫn thiếu dữ kiện.",
                original_reading="Quẻ nghiêng về việc chưa vội.",
                target_card=target,
                target_insight="Hiện tại còn mơ hồ.",
                clarifier_card=clarifier,
                reader_style="auto",
                user_name="Mai",
            )

        self.assertIsInstance(result, TarotClarifierResult)
        self.assertIn(target.card.name_vi, result.full_reading)
        self.assertIn(clarifier.card.name_vi, result.full_reading)
        self.assertIn("không xác nhận", result.full_reading.lower())


class ClarifierRendererTests(unittest.TestCase):
    def test_board_keeps_original_and_adds_target_relation_panel(self):
        original = [
            drawn("major_02", 1, "LÁ 1: QUÁ KHỨ"),
            drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True),
            drawn("major_19", 3, "LÁ 3: TƯƠNG LAI"),
        ]
        clarifier = drawn("major_09", 4, "LÀM RÕ: HIỆN TẠI")
        before = [(c.card.id, c.is_reversed) for c in original]
        state = ClarifierBoardState(
            spread_key="ppf",
            drawn_cards=tuple(original),
            target_position_index=1,
            clarifier_card=clarifier,
            key_card_id="major_19",
        )

        with patch("features.tarot.renderer.ensure_card_asset", return_value=None):
            buffer = render_clarifier_board_to_bytes(state)

        self.assertLess(len(buffer.getvalue()), 8 * 1024 * 1024)
        with Image.open(buffer) as image:
            self.assertEqual(image.size, (1800, 1200))
            self.assertEqual(image.mode, "RGB")
        self.assertEqual(before, [(c.card.id, c.is_reversed) for c in original])


class FakeManager:
    def __init__(self):
        self.saved = []
        self.tasks = set()

    async def get_user_recent_card_ids(self, user_id):
        return []

    def create_ai_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def cancel_ai_task(self, task):
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def save_tarot_clarifier(self, **kwargs):
        self.saved.append(kwargs)


class FakeFollowup:
    def __init__(self, failures=0):
        self.calls = []
        self.failures = failures

    async def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("send failed")
        return SimpleNamespace(id=900)


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        return self


class ClarifierActionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cards = [
            drawn("major_02", 1, "LÁ 1: QUÁ KHỨ"),
            drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True),
            drawn("major_19", 3, "LÁ 3: TƯƠNG LAI"),
        ]
        self.rich = TarotReadingResult(
            full_reading="Quẻ gốc.",
            is_valid=True,
            suggested_clarifier_targets=[
                TarotClarifierTarget(position_id="2", reason="Cần làm rõ hiện tại.")
            ],
        )

    def make_view(self, manager):
        return TarotResultActionView(
            author_id=1,
            author_name="Mai",
            drawn_cards=self.cards,
            question="Tôi nên đi tiếp thế nào?",
            context="Đang cân nhắc.",
            ai_reading="Quẻ gốc.",
            reader_style="auto",
            spread_key="ppf",
            tarot_manager=manager,
            guild_id=10,
            channel_id=20,
            reading_result=self.rich,
        )

    async def test_picker_prioritizes_ai_suggested_target(self):
        view = self.make_view(FakeManager())
        picker = TarotClarifierTargetView(view, FakeMessage())
        self.assertTrue(picker.target_select.options[0].label.startswith("✨ 2."))
        self.assertIn("Asumi gợi ý", picker.target_select.options[0].description)

    async def test_success_consumes_exactly_one_clarifier_after_delivery(self):
        manager = FakeManager()
        view = self.make_view(manager)
        interaction = SimpleNamespace(
            followup=FakeFollowup(),
        )
        origin = FakeMessage()
        ai_result = TarotClarifierResult(
            relationship="Hai lá bổ sung nhau.",
            clarity="Điểm cần chậm lại rõ hơn.",
            effect="Củng cố",
            practical_implication="Kiểm tra thêm dữ kiện.",
            uncertainty="Kết quả vẫn chưa cố định.",
            full_reading="Clarifier reading",
        )

        with patch(
            "features.tarot.tarot_view.generate_clarifier_interpretation",
            new=AsyncMock(return_value=ai_result),
        ), patch(
            "features.tarot.tarot_view.render_clarifier_board_to_bytes",
            return_value=io.BytesIO(b"fake-png"),
        ):
            ok = await view.run_clarifier(interaction, 1, origin)

        self.assertTrue(ok)
        self.assertTrue(view.has_used_clarifier)
        self.assertTrue(view.clarifier_button.disabled)
        self.assertEqual(view.clarifier_button.label, "✓ Đã làm rõ")
        self.assertEqual(len(manager.saved), 1)
        self.assertEqual(len(interaction.followup.calls), 1)
        self.assertEqual(len(origin.edits), 1)

        second = await view.run_clarifier(interaction, 0, origin)
        self.assertFalse(second)
        self.assertEqual(len(manager.saved), 1)

    async def test_delivery_failure_does_not_consume_clarifier(self):
        manager = FakeManager()
        view = self.make_view(manager)
        interaction = SimpleNamespace(
            followup=FakeFollowup(failures=2),
        )
        origin = FakeMessage()
        ai_result = TarotClarifierResult(full_reading="Clarifier reading")

        with patch(
            "features.tarot.tarot_view.generate_clarifier_interpretation",
            new=AsyncMock(return_value=ai_result),
        ), patch(
            "features.tarot.tarot_view.render_clarifier_board_to_bytes",
            return_value=io.BytesIO(b"fake-png"),
        ):
            ok = await view.run_clarifier(interaction, 1, origin)

        self.assertFalse(ok)
        self.assertFalse(view.has_used_clarifier)
        self.assertFalse(view.clarifier_button.disabled)
        self.assertEqual(manager.saved, [])


if __name__ == "__main__":
    unittest.main()
