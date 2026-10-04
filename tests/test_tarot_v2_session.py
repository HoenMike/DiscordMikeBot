import asyncio
import unittest

import discord

from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, TAROT_DECK
from features.tarot.reading.session import (
    build_ai_ready_status,
    build_micro_reveal,
    build_reveal_progress,
    compact_flip_label,
)
from features.tarot.tarot_view import TarotFlipView


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
        self.assertIn("2 · LÁ 2: HIỆN TẠI", text)
        self.assertIn(card.card.name_vi, text)
        self.assertIn("Ngược", text)
        self.assertIn(card.card.keywords_reversed[0], text)

    def test_compact_labels_are_mobile_friendly(self):
        self.assertEqual(compact_flip_label(0, False), "1")
        self.assertEqual(compact_flip_label(9, True), "✓ 10")
        self.assertIn("Luận giải đã sẵn sàng", build_ai_ready_status(True))


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
        self.assertIn("FACE DOWN", embed.footer.text)

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
        self.assertIn("REVEALING", embed.footer.text)

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


if __name__ == "__main__":
    unittest.main()
