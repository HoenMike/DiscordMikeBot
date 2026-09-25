import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from core.branding import BOT_BRAND_NAME, runtime_bot_name
from core.version import CURRENT_VERSION
from features.embed.cog import EmbedCog
from features.embed.builder import PostData, NSFWFilter, build_embed
from features.embed.result import PreviewResult
from features.embed.validator import is_generic_or_login_preview, validate_via_og_metadata, find_valid_proxy
from features.tarot.ai import extract_question_mentions_context, _build_tarot_prompt, parse_tarot_ai_response
from features.tarot.deck import READER_STYLES
from features.tarot.tarot_view import build_reading_payload


def message():
    channel = SimpleNamespace(id=20, is_nsfw=lambda: False)
    return SimpleNamespace(
        id=10, guild=SimpleNamespace(id=30), channel=channel,
        author=SimpleNamespace(display_name="Mai"), jump_url="https://discord.com/channels/30/20/10",
    )


class PreviewClassifierTests(unittest.TestCase):
    def test_facebook_login_and_generic_cards(self):
        for title, description in (
            ("Log in or sign up to view", ""),
            ("Facebook", "See posts, photos and more on Facebook."),
            ("Facebook", ""),
        ):
            self.assertTrue(is_generic_or_login_preview(title, description, platform_key="facebook"))
        self.assertTrue(is_generic_or_login_preview(final_url="https://facebook.com/checkpoint/123", platform_key="facebook"))

    def test_post_specific_text_remains_valid(self):
        self.assertFalse(is_generic_or_login_preview("Mai posted a story", "A real post about a trip", platform_key="facebook"))
        self.assertFalse(is_generic_or_login_preview("Facebook", "Mai wrote about her trip today", platform_key="facebook"))

    def test_brand_and_legacy_mentions(self):
        self.assertEqual(CURRENT_VERSION, "2.8.0")
        self.assertEqual(runtime_bot_name(None), BOT_BRAND_NAME)
        for query in ("@Asumi nghĩ sao?", "Asumi nghĩ sao?", "MikeDaBot nghĩ sao?"):
            clean, context = extract_question_mentions_context(query, "Mai")
            self.assertIn("Asumi", clean)
            self.assertIn("Chính Bạn", context)
        self.assertEqual(set(READER_STYLES), {"auto", "neutral", "healer", "chaos"})
        self.assertTrue(all("Orion" not in value["name"] and "Celeste" not in value["name"] and "Jester" not in value["name"] for value in READER_STYLES.values()))
        prompt = _build_tarot_prompt("daily", "Daily", [], None, "Mai")
        self.assertIn("Bạn là Asumi", prompt)
        self.assertNotIn("Orion", prompt)
        malformed = parse_tarot_ai_response('{"is_valid": false, "full_reading": "Xin lỗi"')
        self.assertNotIn('{"is_valid"', malformed[0])

    def test_spoiler_and_long_tarot_output_guards(self):
        post = PostData(platform="facebook", text="A || secret", media_urls=["https://cdn.example/post.jpg"], is_spoiler=True)
        filtered = NSFWFilter().process(post, SimpleNamespace(is_nsfw=lambda: False), {})
        embed = build_embed(post, filtered)
        self.assertTrue(filtered.should_spoiler_media)
        self.assertFalse(bool(embed.image))
        self.assertTrue(embed.description.startswith("||"))
        cards = discord.Embed(title="Cards", description="Card descriptions")
        embeds, attachment = build_reading_payload(cards, "x" * 12000, "Reading", "Asumi")
        self.assertIsNotNone(attachment)
        self.assertLessEqual(sum(len(item) for item in embeds), 6000)
        attachment.close()


class EmbedPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = EmbedCog(SimpleNamespace(config_manager=None))
        self.cog.session = object()
        self.msg = message()

    async def test_http_metadata_rejects_login_logo_but_accepts_post(self):
        class ResponseContext:
            def __init__(self, html):
                self.status = 200
                self.headers = {"Content-Type": "text/html"}
                self.url = "https://facebed.com/post/1"
                self.content = SimpleNamespace(read=AsyncMock(return_value=html.encode()))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        def session(html):
            return SimpleNamespace(get=lambda *_, **__: ResponseContext(html))

        login = '<meta property="og:title" content="Facebook"><meta property="og:description" content="See posts, photos and more on Facebook."><meta property="og:image" content="https://cdn.example/logo.jpg">'
        post = '<meta property="og:title" content="Mai posted a story"><meta property="og:description" content="Photos from the trip"><meta property="og:image" content="https://cdn.example/post.jpg">'
        self.assertEqual(await validate_via_og_metadata(session(login), "https://facebed.com/post/1", "facebook"), (False, False))
        self.assertEqual(await validate_via_og_metadata(session(post), "https://facebed.com/post/1", "facebook"), (True, False))

    async def test_proxy_search_does_not_revalidate_failed_domains(self):
        tried = set()
        with patch("features.embed.validator.validate_via_og_metadata", new=AsyncMock(side_effect=[(False, False), (True, False)])) as validate:
            url, _ = await find_valid_proxy(
                object(), "https://facebook.com/post/1", "facebook",
                guild_proxy_domains=["facebed.com", "facebed.seria.moe"],
                excluded_domains=tried, attempted_domains=tried,
            )
            self.assertEqual(url, "https://facebed.seria.moe/post/1")
            self.assertEqual(tried, {"facebed.com", "facebed.seria.moe"})
            self.assertEqual(validate.await_count, 2)

    async def test_generic_discord_card_rejected(self):
        card = discord.Embed(title="Facebook", description="See posts, photos and more on Facebook.", url="https://facebook.com/post/1")
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=SimpleNamespace(embeds=[card])))
        preview = SimpleNamespace(id=40, channel=channel)
        with patch("features.embed.cog._UNFURL_DELAYS", (0,)):
            self.assertEqual(await self.cog._verify_proxy_unfurl(10, preview, "facebook"), (False, "generic_or_login_card"))

    async def test_send_without_unfurl_is_not_success(self):
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=SimpleNamespace(embeds=[])))
        preview = SimpleNamespace(id=40, channel=channel)
        with patch("features.embed.cog._UNFURL_DELAYS", (0, 0)):
            self.assertEqual(await self.cog._verify_proxy_unfurl(10, preview, "facebook"), (False, "unfurl_timeout"))

    async def test_second_proxy_can_win_after_first_unusable(self):
        first = SimpleNamespace(id=40)
        second = SimpleNamespace(id=41)
        self.cog._send_embed_preview = AsyncMock(side_effect=[first, second])
        self.cog._verify_proxy_unfurl = AsyncMock(side_effect=[(False, "generic_or_login_card"), (True, "usable_embed")])
        self.cog._discard_preview = AsyncMock()
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(side_effect=[
            ("https://facebed.com/post/1", False),
            ("https://facebed.seria.moe/post/1", False),
        ])):
            result = await self.cog._try_proxy_chain(self.msg, "facebook", "https://facebook.com/post/1", {})
        self.assertTrue(result.success)
        self.assertEqual(result.proxy_domain, "facebed.seria.moe")
        self.assertTrue(result.unfurl_verified)
        self.cog._discard_preview.assert_awaited_once_with(10, first)

    async def test_all_proxies_fail_then_ytdlp_succeeds(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(reason="unfurl_timeout"))
        self.cog._try_ytdlp_fallback = AsyncMock(return_value=True)
        result = await self.cog._run_fallback_chain(self.msg, "facebook", "url", None, {})
        self.assertEqual(result.tier, "ytdlp")
        self.assertTrue(result.success and result.used_fallback)
        self.assertEqual(result.fallback_reason, "unfurl_timeout")

    async def test_nsfw_block_stops_fallback_without_false_success(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=PreviewResult("blocked", "api", "nsfw_blocked"))
        self.cog._try_proxy_chain = AsyncMock()
        self.cog._try_ytdlp_fallback = AsyncMock()
        result = await self.cog._run_fallback_chain(self.msg, "facebook", "url", None, {})
        self.assertEqual(result.status, "blocked")
        self.assertFalse(result.success)
        self.cog._try_proxy_chain.assert_not_awaited()
        self.cog._try_ytdlp_fallback.assert_not_awaited()

    async def test_suppression_requires_usable_or_blocked_result(self):
        msg = message()
        msg.author.bot = False
        msg.author.id = 50
        msg.author.display_avatar = SimpleNamespace(url="avatar")
        msg.guild.name = "Server"
        msg.channel.name = "channel"
        msg.content = "https://facebook.com/post/1"
        msg.edit = AsyncMock()
        self.cog._detect_urls = lambda _: [("facebook", "https://facebook.com/post/1", None, False)]
        self.cog._process_url_with_fallback = AsyncMock()
        fake_bucket = SimpleNamespace(update_rate_limit=lambda: None)
        with patch("features.embed.cog.EMBED_COOLDOWN", SimpleNamespace(get_bucket=lambda _: fake_bucket)), \
             patch("core.activity_logger.activity_logger.log", MagicMock()):
            self.cog._process_url_with_fallback.return_value = PreviewResult(reason="unfurl_timeout")
            await self.cog.on_message(msg)
            msg.edit.assert_not_awaited()
            msg.edit.reset_mock()
            self.cog._process_url_with_fallback.return_value = PreviewResult("blocked", "api", "nsfw_blocked")
            await self.cog.on_message(msg)
            msg.edit.assert_awaited_once_with(suppress=True)

    async def test_cancellation_removes_temporary_preview(self):
        waiting = asyncio.Event()
        preview = SimpleNamespace(id=40)
        self.cog._send_embed_preview = AsyncMock(return_value=preview)
        self.cog._discard_preview = AsyncMock()

        async def verify(*_):
            waiting.set()
            await asyncio.Event().wait()

        self.cog._verify_proxy_unfurl = verify
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://facebed.com/post/1", False))):
            task = asyncio.create_task(self.cog._try_proxy_chain(self.msg, "facebook", "url", {}))
            await waiting.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.cog._discard_preview.assert_awaited_once_with(10, preview)

    async def test_origin_delete_during_verification_stops_fallback(self):
        waiting = asyncio.Event()
        preview = SimpleNamespace(id=40)
        self.cog.bot.user = SimpleNamespace(id=1)
        self.cog.bot.get_channel = lambda _: None
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_ytdlp_fallback = AsyncMock()
        self.cog._send_embed_preview = AsyncMock(return_value=preview)
        self.cog._discard_preview = AsyncMock()

        async def verify(*_):
            waiting.set()
            await asyncio.Event().wait()

        self.cog._verify_proxy_unfurl = verify
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://facebed.com/post/1", False))), \
             patch("core.activity_logger.activity_logger.log", MagicMock()):
            task = asyncio.create_task(self.cog._run_fallback_chain(self.msg, "facebook", "url", None, {}))
            self.cog._in_flight_tasks[10] = task
            await waiting.wait()
            await self.cog.on_raw_message_delete(SimpleNamespace(message_id=10, channel_id=20, guild_id=30))
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.cog._discard_preview.assert_awaited_once_with(10, preview)
        self.cog._try_ytdlp_fallback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
