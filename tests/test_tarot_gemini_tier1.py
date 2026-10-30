"""Regression coverage for Gemini Tier 1 Tarot routing and honest fallback UX."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from core.constants import DEFAULT_AI_FALLBACK_MODELS, DEFAULT_GEMINI_TAROT_MODEL
from features.tarot.ai import TAROT_GEN_CONFIG, generate_tarot_reading_result
from features.tarot.deck import DrawnCard, SPREAD_DEFINITIONS, TAROT_DECK
from features.tarot.reading.schema import TarotReadingResult
from features.tarot.tarot_view import TarotFlipView


def card():
    return DrawnCard(
        card=TAROT_DECK["major_02"],
        is_reversed=False,
        position_index=0,
        position_title="Phán quyết",
        position_description="Phán quyết",
    )


def ai_reply(text):
    return SimpleNamespace(text=text, candidates=[])


VALID_RESULT = json.dumps({
    "is_valid": True,
    "topic_tag": "love",
    "headline": "Cởi mở với cơ hội mới",
    "core_message": "Lá bài gợi ý một cuộc gặp bất ngờ, không phải lời hứa.",
    "practical_takeaway": ["Nếu thích, hãy bắt chuyện một cách tự nhiên."],
    "uncertainty": "Không thể biết chắc sẽ gặp ai.",
}, ensure_ascii=False)


class TarotGeminiTier1Tests(unittest.IsolatedAsyncioTestCase):
    def test_tier1_defaults_have_stable_model_ids(self):
        self.assertEqual(DEFAULT_GEMINI_TAROT_MODEL, "gemini-3.8-flash")
        self.assertEqual(DEFAULT_AI_FALLBACK_MODELS, ["gemini-3.8-flash"])
        self.assertEqual(str(TAROT_GEN_CONFIG.thinking_config.thinking_level).lower().split(".")[-1], "low")

    async def test_success_sets_model_without_fallback(self):
        generate = AsyncMock(return_value=ai_reply(VALID_RESULT))
        with patch("features.tarot.ai.config.TAROT_FALLBACK_MODELS", ["gemini-3.8-flash"]), patch(
            "features.tarot.ai.bounded_ai_generate", new=generate
        ):
            result = await generate_tarot_reading_result("yes_no", [card()], question="Hôm nay có gặp ai không?")
        self.assertFalse(result.ai_fallback)
        self.assertEqual(result.ai_model, "gemini-3.8-flash")
        self.assertEqual(result.headline, "Cởi mở với cơ hội mới")
        self.assertIn("Lá bài gợi ý", result.full_reading)
        self.assertIn("🌫️", result.full_reading)
        self.assertNotIn("🌫\n", result.full_reading)
        self.assertEqual(generate.await_count, 1)

    async def test_empty_and_invalid_answers_keep_dictionary_fallback(self):
        for text in ("", '{"core_message": '):
            generate = AsyncMock(return_value=ai_reply(text))
            with patch("features.tarot.ai.bounded_ai_generate", new=generate):
                result = await generate_tarot_reading_result("yes_no", [card()])
            self.assertTrue(result.ai_fallback)
            self.assertEqual(result.ai_model, "")
            self.assertEqual(generate.await_count, 1)
            self.assertEqual(generate.await_args.kwargs["model"], "gemini-3.8-flash")

    async def test_schema_rejection_retries_same_model_without_schema(self):
        generate = AsyncMock(side_effect=[
            RuntimeError("400 response_schema unsupported"), ai_reply(VALID_RESULT)
        ])
        with patch("features.tarot.ai.config.TAROT_FALLBACK_MODELS", ["gemini-3.8-flash"]), patch(
            "features.tarot.ai.bounded_ai_generate", new=generate
        ):
            result = await generate_tarot_reading_result("yes_no", [card()])
        self.assertEqual(result.ai_model, "gemini-3.8-flash")
        self.assertFalse(result.ai_fallback)
        self.assertEqual(generate.await_count, 2)

    async def test_quota_failure_keeps_local_fallback_and_never_demotes(self):
        generate = AsyncMock(side_effect=RuntimeError("429 RESOURCE_EXHAUSTED"))
        with patch("features.tarot.ai.bounded_ai_generate", new=generate):
            result = await generate_tarot_reading_result("yes_no", [card()])
        self.assertTrue(result.ai_fallback)
        self.assertEqual(result.ai_model, "")
        self.assertEqual(result.ai_error_category, "quota_exceeded")
        self.assertIn("BẢN ĐỌC DỰ PHÒNG", result.full_reading)
        self.assertEqual(generate.await_count, 1)

    async def test_fallback_board_does_not_claim_ai_finished(self):
        task = __import__("asyncio").create_task(__import__("asyncio").sleep(60))
        view = TarotFlipView(
            author_id=1, author_name="Tester", author_avatar_url=None,
            spread_key="yes_no", spread_info=SPREAD_DEFINITIONS["yes_no"],
            drawn_cards=[card()], question="Có gặp ai không?",
            reader_style="auto", ai_task=task, tarot_manager=None,
        )
        source = discord.Embed(title="Cards", description="Phán quyết Yes/No")
        result = TarotReadingResult(full_reading="📖 BẢN ĐỌC DỰ PHÒNG", ai_fallback=True)
        try:
            embeds, _ = view.build_final_payload(source, result.full_reading, reading_result=result)
            self.assertIn("AI CHƯA LUẬN GIẢI", embeds[0].description)
            self.assertNotIn("HOÀN TẤT", embeds[0].description)
            self.assertIn("BẢN ĐỌC DỰ PHÒNG", embeds[1].footer.text)
        finally:
            task.cancel()
            try:
                await task
            except BaseException:
                pass
            view.stop()


if __name__ == "__main__":
    unittest.main()
