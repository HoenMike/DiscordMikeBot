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
from features.embed.ui import EmbedActionView
from features.embed.validator import is_generic_or_login_preview, validate_via_og_metadata, find_valid_proxy
from features.tarot.ai import extract_question_mentions_context, _build_tarot_prompt, parse_tarot_ai_response
from features.tarot.deck import READER_STYLES
from features.tarot.tarot_view import build_reading_payload


def message():
    channel = SimpleNamespace(id=20, is_nsfw=lambda: False)
    return SimpleNamespace(
        id=10, guild=SimpleNamespace(id=30), channel=channel,
        author=SimpleNamespace(id=50, display_name="Mai"), jump_url="https://discord.com/channels/30/20/10",
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
        self.assertEqual(CURRENT_VERSION, "3.4.0")
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

    async def test_transient_generic_card_can_become_usable_before_grace_window_ends(self):
        generic = discord.Embed(title="Facebook", description="See posts, photos and more on Facebook.", url="https://facebook.com/post/1")
        usable = discord.Embed(title="Mai posted a reel", description="Video preview ready", url="https://facebed.com/post/1")
        usable.set_image(url="https://cdn.example/video-thumb.jpg")
        channel = SimpleNamespace(fetch_message=AsyncMock(side_effect=[
            SimpleNamespace(embeds=[generic]),
            SimpleNamespace(embeds=[usable]),
        ]))
        preview = SimpleNamespace(id=40, channel=channel)
        with patch("features.embed.cog._UNFURL_DELAYS", (0, 0)):
            self.assertEqual(await self.cog._verify_proxy_unfurl(10, preview, "facebook"), (True, "usable_embed"))

    async def test_send_without_unfurl_is_not_success(self):
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=SimpleNamespace(embeds=[])))
        preview = SimpleNamespace(id=40, channel=channel)
        with patch("features.embed.cog._UNFURL_DELAYS", (0, 0)):
            self.assertEqual(await self.cog._verify_proxy_unfurl(10, preview, "facebook"), (False, "unfurl_timeout"))

    async def test_facebook_proxy_sends_raw_url_and_button_without_auto_verify(self):
        preview = SimpleNamespace(id=40)
        self.cog._send_embed_preview = AsyncMock(return_value=preview)
        self.cog._verify_proxy_unfurl = AsyncMock()
        self.cog._discard_preview = AsyncMock()
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://facebed.com/post/1", False))) as find_proxy:
            result = await self.cog._try_proxy_chain(self.msg, "facebook", "https://facebook.com/post/1", {})

        self.assertTrue(result.success)
        self.assertEqual(result.proxy_domain, "facebed.com")
        self.assertEqual(result.preview_message_id, 40)
        find_proxy.assert_awaited_once()
        self.cog._verify_proxy_unfurl.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()

        sent_kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIsInstance(sent_kwargs["view"], EmbedActionView)
        self.assertIn("[facebed.com](https://facebed.com/post/1)", sent_kwargs["content"])
        self.assertNotIn("\nhttps://facebed.com/post/1", sent_kwargs["content"])
        self.assertIsNone(sent_kwargs["view"].reload_button.label)
        self.assertEqual(str(sent_kwargs["view"].reload_button.emoji), "🔄")
        self.assertIsNone(sent_kwargs["view"].remove_button.label)
        self.assertEqual(str(sent_kwargs["view"].remove_button.emoji), "❌")
        self.assertIn("facebed.com", sent_kwargs["view"].payload["tried_domains"])

    async def test_embed_action_buttons_are_owner_only_and_reload(self):
        view = self.cog._manual_fallback_view(
            self.msg,
            "facebook",
            "https://facebook.com/post/1",
            tried_domains={"facebed.com"},
        )
        self.assertIsInstance(view, EmbedActionView)
        self.assertIsNone(view.reload_button.label)
        self.assertEqual(str(view.reload_button.emoji), "🔄")
        self.assertIsNone(view.remove_button.label)
        self.assertEqual(str(view.remove_button.emoji), "❌")

        denied = SimpleNamespace(
            user=SimpleNamespace(id=999),
            response=SimpleNamespace(send_message=AsyncMock()),
        )
        self.assertFalse(await view.interaction_check(denied))
        denied.response.send_message.assert_awaited_once()
        self.assertTrue(denied.response.send_message.await_args.kwargs["ephemeral"])

        current_preview = SimpleNamespace(id=40, edit=AsyncMock())
        allowed = SimpleNamespace(
            user=SimpleNamespace(id=50),
            response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
            message=current_preview,
        )
        self.assertTrue(await view.interaction_check(allowed))

        self.cog.reload_embed = AsyncMock(return_value=PreviewResult(
            "success",
            "proxy",
            "proxy_rolled",
            "facebook",
            proxy_domain="facebed.seria.moe",
            origin_message_id=10,
            preview_message_id=41,
            used_fallback=True,
            fallback_reason="manual_proxy_roll",
        ))
        await view._reload(allowed)
        self.cog.reload_embed.assert_awaited_once_with(
            view.payload,
            current_preview=current_preview,
        )
        allowed.response.edit_message.assert_awaited_once()
        allowed.followup.send.assert_awaited_once()
        self.assertTrue(allowed.followup.send.await_args.kwargs["ephemeral"])

    async def test_action_view_is_available_for_non_facebook_provider(self):
        view = self.cog._manual_fallback_view(
            self.msg,
            "twitter",
            "https://x.com/example/status/123",
        )
        self.assertIsInstance(view, EmbedActionView)
        self.assertEqual(view.payload["platform"], "twitter")
        self.assertIsNone(view.reload_button.label)
        self.assertEqual(str(view.reload_button.emoji), "🔄")
        self.assertIsNone(view.remove_button.label)
        self.assertEqual(str(view.remove_button.emoji), "❌")

    async def test_facebook_does_not_auto_roll_after_first_proxy_is_sent(self):
        first = SimpleNamespace(id=40)
        self.cog._send_embed_preview = AsyncMock(return_value=first)
        self.cog._verify_proxy_unfurl = AsyncMock()
        self.cog._discard_preview = AsyncMock()
        find_proxy = AsyncMock(side_effect=[
            ("https://facebed.com/post/1", False),
            ("https://facebed.seria.moe/post/1", False),
        ])
        with patch("features.embed.cog.find_valid_proxy", new=find_proxy):
            result = await self.cog._try_proxy_chain(self.msg, "facebook", "https://facebook.com/post/1", {})

        self.assertTrue(result.success)
        self.assertEqual(result.proxy_domain, "facebed.com")
        self.assertEqual(find_proxy.await_count, 1)
        self.cog._verify_proxy_unfurl.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()

    async def test_manual_proxy_roll_moves_to_next_proxy_without_ytdlp(self):
        channel = SimpleNamespace(id=20, is_nsfw=lambda: False)
        origin = SimpleNamespace(
            id=10,
            guild=SimpleNamespace(id=30, name="Server"),
            channel=channel,
            author=SimpleNamespace(
                id=50,
                display_name="Mai",
                display_avatar=SimpleNamespace(url="avatar"),
            ),
            jump_url="https://discord.com/channels/30/20/10",
            content="https://facebook.com/post/1",
        )
        channel.fetch_message = AsyncMock(return_value=origin)
        self.cog.bot.get_channel = lambda _: channel
        self.cog.bot.fetch_channel = AsyncMock(return_value=channel)

        current_preview = SimpleNamespace(id=40, channel=channel)
        new_preview = SimpleNamespace(id=41, channel=channel)
        self.cog._send_embed_preview = AsyncMock(return_value=new_preview)
        self.cog._discard_preview = AsyncMock(return_value=True)
        self.cog._try_ytdlp_fallback = AsyncMock()

        payload = {
            "origin_id": 10,
            "channel_id": 20,
            "author_id": 50,
            "platform": "facebook",
            "url": "https://facebook.com/post/1",
            "is_spoiler": False,
            "tried_domains": ["facebed.com"],
        }
        with patch(
            "features.embed.cog.find_valid_proxy",
            new=AsyncMock(return_value=("https://facebed.seria.moe/post/1", False)),
        ) as find_proxy:
            result = await self.cog.roll_facebook_proxy(
                payload,
                current_preview=current_preview,
            )

        self.assertTrue(result.success)
        self.assertEqual(result.tier, "proxy")
        self.assertEqual(result.proxy_domain, "facebed.seria.moe")
        self.cog._try_ytdlp_fallback.assert_not_awaited()
        self.cog._discard_preview.assert_awaited_once_with(10, current_preview)
        sent_kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIn("[facebed.seria.moe](https://facebed.seria.moe/post/1)", sent_kwargs["content"])
        self.assertIsInstance(sent_kwargs["view"], EmbedActionView)
        self.assertIn("facebed.com", find_proxy.await_args.kwargs["excluded_domains"])
        self.assertIn("facebed.seria.moe", sent_kwargs["view"].payload["tried_domains"])

    async def test_facebook_is_not_supported_by_ytdlp_fallback_anymore(self):
        result = await self.cog._try_ytdlp_fallback(
            self.msg,
            "facebook",
            "https://facebook.com/post/1",
            {},
        )
        self.assertFalse(result)

    async def test_manual_proxy_roll_stops_when_no_proxy_remains_and_keeps_preview(self):
        channel = SimpleNamespace(id=20, is_nsfw=lambda: False)
        origin = SimpleNamespace(
            id=10,
            guild=SimpleNamespace(id=30, name="Server"),
            channel=channel,
            author=SimpleNamespace(
                id=50,
                display_name="Mai",
                display_avatar=SimpleNamespace(url="avatar"),
            ),
            jump_url="https://discord.com/channels/30/20/10",
            content="https://facebook.com/post/1",
        )
        channel.fetch_message = AsyncMock(return_value=origin)
        self.cog.bot.get_channel = lambda _: channel
        self.cog.bot.fetch_channel = AsyncMock(return_value=channel)
        current_preview = SimpleNamespace(id=40, channel=channel)
        self.cog._discard_preview = AsyncMock(return_value=True)
        self.cog._send_embed_preview = AsyncMock()
        self.cog._try_ytdlp_fallback = AsyncMock()

        payload = {
            "origin_id": 10,
            "channel_id": 20,
            "author_id": 50,
            "platform": "facebook",
            "url": "https://facebook.com/post/1",
            "is_spoiler": False,
            "tried_domains": ["facebed.com", "facebed.seria.moe"],
        }
        with patch(
            "features.embed.cog.find_valid_proxy",
            new=AsyncMock(return_value=(None, False)),
        ):
            result = await self.cog.roll_facebook_proxy(
                payload,
                current_preview=current_preview,
            )

        self.assertEqual(result.status, "action_required")
        self.assertEqual(result.reason, "no_more_proxy")
        self.cog._send_embed_preview.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()
        self.cog._try_ytdlp_fallback.assert_not_awaited()

    async def test_non_facebook_proxy_success_includes_action_view(self):
        preview = SimpleNamespace(id=40)
        self.cog._send_embed_preview = AsyncMock(return_value=preview)
        self.cog._verify_proxy_unfurl = AsyncMock(return_value=(True, "usable_embed"))
        with patch(
            "features.embed.cog.find_valid_proxy",
            new=AsyncMock(return_value=("https://fxtwitter.com/example/status/123", False)),
        ):
            result = await self.cog._try_proxy_chain(
                self.msg,
                "twitter",
                "https://x.com/example/status/123",
                {},
            )

        self.assertTrue(result.success)
        sent_kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIsInstance(sent_kwargs["view"], EmbedActionView)
        self.assertEqual(sent_kwargs["view"].payload["platform"], "twitter")

    async def test_reload_non_facebook_reprocesses_and_replaces_current_preview(self):
        channel = SimpleNamespace(id=20, is_nsfw=lambda: False)
        origin = SimpleNamespace(
            id=10,
            guild=SimpleNamespace(id=30, name="Server"),
            channel=channel,
            author=SimpleNamespace(
                id=50,
                display_name="Mai",
                display_avatar=SimpleNamespace(url="avatar"),
            ),
            jump_url="https://discord.com/channels/30/20/10",
            content="https://x.com/example/status/123",
        )
        channel.fetch_message = AsyncMock(return_value=origin)
        self.cog.bot.get_channel = lambda _: channel
        self.cog.bot.fetch_channel = AsyncMock(return_value=channel)
        self.cog._run_fallback_chain = AsyncMock(return_value=PreviewResult(
            "success",
            "proxy",
            "usable_embed",
            "twitter",
            proxy_domain="fxtwitter.com",
            origin_message_id=10,
            preview_message_id=41,
            unfurl_verified=True,
        ))
        self.cog._discard_preview = AsyncMock(return_value=True)
        current_preview = SimpleNamespace(id=40, channel=channel)

        result = await self.cog.reload_embed(
            {
                "origin_id": 10,
                "channel_id": 20,
                "author_id": 50,
                "platform": "twitter",
                "url": "https://x.com/example/status/123",
                "is_spoiler": False,
            },
            current_preview=current_preview,
        )

        self.assertTrue(result.success)
        self.cog._run_fallback_chain.assert_awaited_once()
        self.cog._discard_preview.assert_awaited_once_with(10, current_preview)

    async def test_remove_embed_restores_native_and_cleans_asumi_previews(self):
        origin = SimpleNamespace(
            id=10,
            guild=SimpleNamespace(id=30, name="Server"),
            author=SimpleNamespace(
                id=50,
                display_name="Mai",
                display_avatar=SimpleNamespace(url="avatar"),
            ),
            content="https://x.com/example/status/123",
            edit=AsyncMock(),
        )
        channel = SimpleNamespace(
            id=20,
            name="channel",
            fetch_message=AsyncMock(return_value=origin),
            get_partial_message=lambda preview_id: SimpleNamespace(id=preview_id),
        )
        origin.channel = channel
        self.cog.bot.get_channel = lambda _: channel
        self.cog.bot.fetch_channel = AsyncMock(return_value=channel)
        self.cog._origin_to_preview_map[10] = [(20, 40), (20, 41)]
        self.cog._discard_preview = AsyncMock(return_value=True)

        result = await self.cog.revert_embed({
            "origin_id": 10,
            "channel_id": 20,
            "author_id": 50,
            "platform": "twitter",
            "url": "https://x.com/example/status/123",
        })

        self.assertTrue(result.success)
        origin.edit.assert_awaited_once_with(suppress=False)
        self.assertEqual(self.cog._discard_preview.await_count, 2)

    async def test_facebook_proxy_failure_offers_manual_fallback_without_auto_ytdlp(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(reason="unfurl_timeout"))
        self.cog._try_ytdlp_fallback = AsyncMock()
        self.cog._offer_manual_fallback = AsyncMock(return_value=PreviewResult(
            "action_required", "manual", "manual_fallback_offered", "facebook",
            origin_message_id=10, fallback_reason="unfurl_timeout",
        ))
        result = await self.cog._run_fallback_chain(self.msg, "facebook", "url", None, {})
        self.assertEqual(result.status, "action_required")
        self.assertEqual(result.tier, "manual")
        self.cog._try_ytdlp_fallback.assert_not_awaited()

    async def test_non_facebook_proxy_failure_still_uses_auto_ytdlp(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(reason="unfurl_timeout"))
        self.cog._try_ytdlp_fallback = AsyncMock(return_value=True)
        result = await self.cog._run_fallback_chain(self.msg, "twitter", "url", None, {})
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
            msg.edit.reset_mock()
            self.cog._process_url_with_fallback.return_value = PreviewResult(
                "action_required", "proxy", "unfurl_timeout", "facebook", origin_message_id=10
            )
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
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://fxtwitter.com/post/1", False))):
            task = asyncio.create_task(self.cog._try_proxy_chain(self.msg, "twitter", "url", {}))
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
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://fxtwitter.com/post/1", False))), \
             patch("core.activity_logger.activity_logger.log", MagicMock()):
            task = asyncio.create_task(self.cog._run_fallback_chain(self.msg, "twitter", "url", None, {}))
            self.cog._in_flight_tasks[10] = task
            await waiting.wait()
            await self.cog.on_raw_message_delete(SimpleNamespace(message_id=10, channel_id=20, guild_id=30))
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.cog._discard_preview.assert_awaited_once_with(10, preview)
        self.cog._try_ytdlp_fallback.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
