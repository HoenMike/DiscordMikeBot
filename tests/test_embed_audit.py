import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import discord
from features.embed.cog import EmbedCog, PreviewSendUncertain
from features.embed.result import PreviewSafety
from features.embed.validator import is_generic_or_login_preview
from features.embed.builder import PostData


def http_error(cls=discord.HTTPException):
    return cls(NS(status=403 if cls is discord.Forbidden else 500, reason="test"), "test")


class AuditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = EmbedCog(NS(config_manager=None))
        self.cog.session = object()
        self.channel = NS(id=2, is_nsfw=lambda: False, send=AsyncMock())
        self.message = NS(id=1, channel=self.channel, guild=NS(id=3, filesize_limit=1000),
                          author=NS(display_name="A"), jump_url="https://discord.com/channels/3/2/1")
        self.preview = NS(id=4, channel=self.channel, delete=AsyncMock())
        self.channel.send.return_value = self.preview

    async def test_cleanup_retains_mapping_on_failure(self):
        for exc in (http_error(), http_error(discord.Forbidden)):
            self.cog._register_preview(1, 2, 4)
            self.preview.delete.side_effect = exc
            self.assertFalse(await self.cog._discard_preview(1, self.preview))
            self.assertIn(4, self.cog._preview_to_origin_map)
        self.preview.delete.side_effect = None
        self.assertTrue(await self.cog._discard_preview(1, self.preview))
        self.assertNotIn(4, self.cog._preview_to_origin_map)

    async def test_cleanup_notfound_unregisters(self):
        self.cog._register_preview(1, 2, 4)
        self.preview.delete.side_effect = discord.NotFound(NS(status=404, reason="gone"), "gone")
        self.assertTrue(await self.cog._discard_preview(1, self.preview))
        self.assertNotIn(1, self.cog._origin_to_preview_map)

    async def test_cancel_during_delete_waits_for_cleanup(self):
        started, finish = asyncio.Event(), asyncio.Event()
        async def delete():
            started.set()
            await finish.wait()
        self.preview.delete.side_effect = delete
        self.cog._register_preview(1, 2, 4)
        task = asyncio.create_task(self.cog._discard_preview(1, self.preview))
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        self.assertIn(4, self.cog._preview_to_origin_map)
        finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertNotIn(4, self.cog._preview_to_origin_map)

    async def test_origin_deleted_before_send(self):
        self.cog._deleted_message_ids[1] = True
        self.assertIsNone(await self.cog._send_embed_preview(self.message, content="x"))
        self.channel.send.assert_not_awaited()

    async def test_cancel_outstanding_send_resolves_and_cleans(self):
        for deletion_fails in (False, True):
            with self.subTest(deletion_fails=deletion_fails):
                started, accepted = asyncio.Event(), asyncio.Event()
                async def send(**kwargs):
                    started.set()
                    await accepted.wait()
                    return self.preview
                self.channel.send.side_effect = send
                self.preview.delete.side_effect = http_error() if deletion_fails else None
                task = asyncio.create_task(self.cog._send_embed_preview(self.message, content="x"))
                await started.wait()
                task.cancel()
                accepted.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(4 in self.cog._preview_to_origin_map, deletion_fails)

    async def test_delayed_unfurl_after_two_empty_fetches(self):
        self.channel.fetch_message = AsyncMock(side_effect=[NS(embeds=[]), NS(embeds=[]), NS(embeds=[discord.Embed(title="Mai: chuyến đi")])])
        with patch("features.embed.cog.asyncio.sleep", new=AsyncMock()) as sleep:
            ok, _ = await self.cog._verify_proxy_unfurl(1, self.preview, "facebook")
        self.assertTrue(ok)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [1, 1.5, 1.5])

    async def test_sticky_nsfw_between_proxies_and_fallback(self):
        safety = PreviewSafety()
        second = NS(id=5, delete=AsyncMock())
        self.cog._send_embed_preview = AsyncMock(side_effect=[self.preview, second])
        self.cog._verify_proxy_unfurl = AsyncMock(side_effect=[(False, "timeout"), (True, "usable")])
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(side_effect=[("https://facebed.com/p", True), ("https://facebed.seria.moe/p", False)])):
            result = await self.cog._try_proxy_chain(self.message, "facebook", "url", {}, safety=safety)
        self.assertTrue(result.success)
        self.assertIn("||", self.cog._send_embed_preview.await_args_list[1].kwargs["content"])
        post = PostData(platform="facebook", text="post", media_urls=["https://cdn/photo.jpg"])
        self.cog._send_embed_preview = AsyncMock(return_value=second)
        self.cog._create_spoiler_file = AsyncMock(return_value=None)
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=post)):
            await self.cog._try_ytdlp_fallback(self.message, "facebook", "url", {}, safety=safety)
        self.assertTrue(post.is_nsfw)
        self.cog._create_spoiler_file.assert_awaited_once()

    async def test_cleanup_failure_stops_next_candidate(self):
        self.preview.delete.side_effect = http_error()
        self.cog._verify_proxy_unfurl = AsyncMock(return_value=(False, "timeout"))
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=("https://facebed.com/p", False))) as find:
            result = await self.cog._try_proxy_chain(self.message, "facebook", "url", {})
        self.assertEqual(result.status, "degraded")
        self.assertEqual(find.await_count, 1)
        self.assertIn(4, self.cog._preview_to_origin_map)

    async def test_send_timeout_is_terminal_and_late_gateway_preview_is_cleaned(self):
        nonce = None
        async def send(**kwargs):
            nonlocal nonce
            nonce = kwargs["nonce"]
            await asyncio.Event().wait()
        self.channel.send.side_effect = send
        self.cog.bot.user = NS(id=99)
        with patch("features.embed.cog._SEND_TIMEOUT", .01):
            with self.assertRaises(PreviewSendUncertain):
                await self.cog._send_embed_preview(self.message, content="x")
        self.assertIn(nonce, self.cog._pending_sends)
        self.preview.nonce = nonce
        self.preview.author = NS(id=99, bot=True)
        await self.cog.on_message(self.preview)
        self.preview.delete.assert_awaited_once()
        self.assertNotIn(nonce, self.cog._pending_sends)
        self.assertNotIn(4, self.cog._preview_to_origin_map)

    async def test_delete_origin_at_each_pipeline_stage(self):
        from contextlib import ExitStack
        from features.embed.result import PreviewResult
        for stage in ("validation", "fetch", "send", "delete", "download", "fallback"):
            with self.subTest(stage=stage), ExitStack() as stack:
                self.setUp()
                entered, release = asyncio.Event(), asyncio.Event()
                self.cog.bot.user = NS(id=99)
                self.cog.bot.get_channel = lambda _: self.channel
                self.channel.get_partial_message = lambda _: self.preview
                self.cog._try_api_fetcher = AsyncMock(return_value=False)
                async def wait(*args, **kwargs):
                    entered.set()
                    await release.wait()
                    return self.preview
                find = AsyncMock(return_value=("https://facebed.com/p", False))
                stack.enter_context(patch("features.embed.cog.find_valid_proxy", new=find))
                stack.enter_context(patch("features.embed.cog._UNFURL_DELAYS", (0,)))
                stack.enter_context(patch("core.activity_logger.activity_logger.log"))
                self.channel.fetch_message = AsyncMock(return_value=NS(embeds=[]))
                if stage == "validation":
                    find.side_effect = wait
                elif stage == "fetch":
                    self.channel.fetch_message.side_effect = wait
                elif stage == "send":
                    self.channel.send.side_effect = wait
                elif stage == "delete":
                    self.preview.delete.side_effect = wait
                else:
                    self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult())
                    if stage == "fallback":
                        stack.enter_context(patch("features.embed.cog.extract_media_ytdlp", new=wait))
                    else:
                        post = PostData(platform="facebook", text="video", media_type="video", media_urls=["https://cdn/v.mp4"])
                        stack.enter_context(patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=post)))
                        self.cog._download_video_file = wait
                task = asyncio.create_task(self.cog._run_fallback_chain(self.message, "facebook", "url", None, {}))
                self.cog._in_flight_tasks[1] = task
                await asyncio.wait_for(entered.wait(), 1)
                deletion = asyncio.create_task(self.cog.on_raw_message_delete(NS(message_id=1, channel_id=2, guild_id=3)))
                await asyncio.sleep(0)
                release.set()
                await deletion
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertNotIn(4, self.cog._preview_to_origin_map)

    async def test_two_failed_proxies_then_real_fallback_send(self):
        from features.embed.result import PreviewResult
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        first, second, final = [NS(id=i, channel=self.channel, delete=AsyncMock()) for i in (4, 5, 6)]
        self.channel.send.side_effect = [first, second, final]
        self.channel.fetch_message = AsyncMock(return_value=NS(embeds=[]))
        post = PostData(platform="facebook", text="Bai viet", media_urls=["https://cdn/image.jpg"])
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(side_effect=[("https://facebed.com/p", False), ("https://facebed.seria.moe/p", False)])), \
             patch("features.embed.cog._UNFURL_DELAYS", (0,)), \
             patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=post)):
            result = await self.cog._run_fallback_chain(self.message, "facebook", "url", None, {})
        self.assertTrue(result.success)
        self.assertEqual(result.tier, "ytdlp")
        first.delete.assert_awaited_once()
        second.delete.assert_awaited_once()
        self.assertEqual(self.cog._origin_to_preview_map[1], [(2, 6)])


class FacebookFixtures(unittest.TestCase):
    def test_contextual_metadata(self):
        fixtures = [
            ("Facebook", "Log into Facebook to start sharing and connecting with your friends, family, and people you know.", {"og:image": "https://cdn/logo.jpg"}, True),
            ("Facebook", "", {"og:image": "https://cdn/facebook-logo.png"}, True),
            ("Facebook", "", {"og:image": "https://cdn/rsrc.php/v3/a.png"}, True),
            ("This content isn't available right now", "", {"og:image": "https://cdn/a.png"}, True),
            ("Mai chia sẻ", 'Tôi gặp lỗi "Log in or sign up to view" hôm qua.', {}, False),
            ("Facebook", "Mai kể về chuyến đi hôm nay", {}, False),
            ("Mai: ảnh du lịch", "", {"og:image": "https://cdn/post123.jpg"}, False),
            ("Facebook", "", {"og:video": "https://cdn/reel.mp4"}, False),
        ]
        for title, desc, tags, expected in fixtures:
            with self.subTest(title=title, desc=desc):
                self.assertEqual(is_generic_or_login_preview(title, desc, meta_tags=tags, platform_key="facebook"), expected)
