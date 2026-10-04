import asyncio
import unittest

import discord

from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, TAROT_DECK
from features.tarot.reading.schema import TarotKeyCard, TarotReadingResult
from features.tarot.reading.followup import TarotSessionState
from features.tarot.reading.session import (
    build_ai_ready_status,
    build_micro_reveal,
    build_reveal_progress,
    compact_flip_label,
)
from features.tarot.tarot_view import TarotFlipView, TarotResultActionView, _unpack_tarot_result


def drawn(card_id: str, position_index: int, position_title: str, reversed_: bool = False) -> DrawnCard:
    return DrawnCard(
        card=TAROT_DECK[card_id],
        is_reversed=reversed_,
        position_index=position_index,
        position_title=position_title,
        position_description=position_title,
    )


class FakeManager:
    async def cancel_ai_task(self, task):
        task.cancel()
        try:
            await task
        except BaseException:
            pass


class FakeMessage:
    def __init__(self):
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)
        return self


class TarotSessionHelperTests(unittest.TestCase):
    def test_progress_preserves_reveal_positions_and_numeric_count(self):
        self.assertEqual(
            build_reveal_progress({0, 2}, 3),
            "● ○ ●   **2 / 3 lá đã lật**",
        )

    def test_micro_reveal_uses_orientation_specific_keywords(self):
        card = drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True)
        text = build_micro_reveal(card, 2)
        self.assertIn("2 · HIỆN TẠI", text)
        self.assertIn(card.card.name_vi, text)
        self.assertIn("Ngược", text)
        self.assertIn(card.card.keywords_reversed[0], text)

    def test_compact_labels_are_mobile_friendly(self):
        self.assertEqual(compact_flip_label(0, False), "1")
        self.assertEqual(compact_flip_label(9, True), "✓ 10")
        self.assertIn("Luận giải đã sẵn sàng", build_ai_ready_status(True))


class TarotRichSessionResultTests(unittest.TestCase):
    def test_rich_result_exposes_key_card_for_final_board(self):
        result = TarotReadingResult(
            full_reading="Reading",
            topic_tag="decision",
            mood_tag="Cân bằng",
            headline="Chưa cần vội",
            is_valid=True,
            key_card=TarotKeyCard(
                card_id="major_18",
                card_name="Mặt Trăng",
                reason="Lá chủ đạo",
            ),
        )
        unpacked = _unpack_tarot_result(result)
        self.assertEqual(unpacked[:5], ("Reading", "decision", "Cân bằng", "Chưa cần vội", True))
        self.assertEqual(unpacked[5], "major_18")


class TarotFlipSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pending_task = asyncio.create_task(asyncio.sleep(60))
        self.cards = [
            drawn("major_02", 1, "LÁ 1: QUÁ KHỨ"),
            drawn("major_18", 2, "LÁ 2: HIỆN TẠI", reversed_=True),
            drawn("major_19", 3, "LÁ 3: TƯƠNG LAI"),
        ]
        self.view = TarotFlipView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            spread_key="ppf",
            spread_info=SPREAD_DEFINITIONS["ppf"],
            drawn_cards=self.cards,
            question="Project này đang đi theo hướng nào?",
            context="Đang cân nhắc thay đổi cách làm.",
            reader_style="auto",
            ai_task=self.pending_task,
            tarot_manager=FakeManager(),
        )

    async def asyncTearDown(self):
        if not self.pending_task.done():
            self.pending_task.cancel()
        try:
            await self.pending_task
        except BaseException:
            pass
        self.view.stop()

    async def test_initial_session_embed_is_face_down_with_progress(self):
        embed = self.view.build_session_embed()
        self.assertIn("0 / 3 lá đã lật", embed.description)
        self.assertIn("Asumi đang đọc mối liên hệ", embed.description)
        self.assertIn("▫️ *Chưa lật*", embed.description)
        self.assertIn("CHỜ LẬT", embed.footer.text)

        labels = [item.label for item in self.view.children if isinstance(item, discord.ui.Button)]
        self.assertEqual(labels, ["1", "2", "3", "✨ Lật hết"])

    async def test_partial_reveal_has_micro_feedback_and_compact_done_button(self):
        self.view.revealed_indices = {1}
        self.view._last_revealed_indices = {1}
        self.view._build_buttons()

        embed = self.view.build_session_embed()
        self.assertIn("1 / 3 lá đã lật", embed.description)
        self.assertIn("✨ Vừa lật", embed.description)
        self.assertIn(self.cards[1].card.name_vi, embed.description)
        self.assertIn("ĐANG LẬT", embed.footer.text)

        labels = [item.label for item in self.view.children if isinstance(item, discord.ui.Button)]
        self.assertEqual(labels, ["1", "✓ 2", "3", "✨ Lật hết"])

    async def test_completed_ai_task_refreshes_ready_indicator_without_new_message(self):
        ready_task = asyncio.create_task(asyncio.sleep(0, result=("reading", "general", "", "", True)))
        view = TarotFlipView(
            author_id=1,
            author_name="Mai",
            author_avatar_url=None,
            spread_key="ppf",
            spread_info=SPREAD_DEFINITIONS["ppf"],
            drawn_cards=self.cards,
            question="Test",
            context=None,
            reader_style="auto",
            ai_task=ready_task,
            tarot_manager=FakeManager(),
        )
        await ready_task

        message = FakeMessage()
        await view.attach_message(message)

        self.assertEqual(len(message.edits), 1)
        self.assertIn("Luận giải đã sẵn sàng", message.edits[0]["embed"].description)
        self.assertIs(message.edits[0]["view"], view)
        view.stop()


class TarotMultiTurnStateTests(unittest.TestCase):
    def test_three_followups_are_bounded_and_keep_order(self):
        state = TarotSessionState(max_followups=3, timeout_seconds=900, last_activity_at=100.0)
        self.assertTrue(state.record_followup("Q1", "A1", now=110.0))
        self.assertTrue(state.record_followup("Q2", "A2", now=120.0))
        self.assertTrue(state.record_followup("Q3", "A3", now=130.0))
        self.assertFalse(state.record_followup("Q4", "A4", now=140.0))
        self.assertEqual(state.remaining_followups, 0)
        self.assertEqual(state.prompt_history(), [("Q1", "A1"), ("Q2", "A2"), ("Q3", "A3")])

    def test_failed_turn_does_not_consume_capacity(self):
        state = TarotSessionState(max_followups=3, timeout_seconds=900, last_activity_at=100.0)
        self.assertFalse(state.record_followup("", "A", now=110.0))
        self.assertFalse(state.record_followup("Q", "", now=110.0))
        self.assertEqual(state.remaining_followups, 3)

    def test_timeout_blocks_followup_and_why(self):
        state = TarotSessionState(timeout_seconds=900, last_activity_at=100.0)
        self.assertFalse(state.can_followup(now=1000.0))
        self.assertFalse(state.mark_why_used(now=1000.0))

    def test_clarifier_and_why_share_same_session_lifecycle(self):
        state = TarotSessionState(timeout_seconds=900, last_activity_at=100.0)
        state.set_clarifier("Target -> Clarifier", now=200.0)
        self.assertEqual(state.clarifier_summary, "Target -> Clarifier")
        self.assertTrue(state.mark_why_used(now=250.0))
        self.assertTrue(state.why_used)
        self.assertEqual(state.last_activity_at, 250.0)


class TarotResultSessionControlTests(unittest.TestCase):
    def test_result_view_exposes_three_turn_followup_and_why(self):
        view = TarotResultActionView(
            author_id=1,
            author_name="Mai",
            drawn_cards=[drawn("major_02", 0, "Lời khuyên")],
            question="Tôi nên chú ý gì?",
            context="Đang cân nhắc.",
            ai_reading="Reading",
            reader_style="auto",
            spread_key="single",
            tarot_manager=FakeManager(),
        )
        custom_ids = {getattr(item, "custom_id", "") for item in view.children}
        self.assertIn("tarot_followup", custom_ids)
        self.assertIn("tarot_why", custom_ids)
        self.assertIn("tarot_clarifier", custom_ids)
        self.assertEqual(view.session_state.max_followups, 3)
        view.stop()


if __name__ == "__main__":
    unittest.main()
