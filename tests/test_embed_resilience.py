"""Facebook video preview resilience, multi-proxy, and final yt-dlp fallback."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord

from core.constants import PROXY_DOMAINS, PLATFORMS
from features.embed.cog import EmbedCog
from features.embed.builder import PostData
from features.embed.result import PreviewResult
from features.embed.validator import build_proxy_url, validate_via_og_metadata


VIDEO_URL = "https://www.facebook.com/share/v/1Ht6IiKfrP/?mibextid=wwXIfr"
REEL_URL = "https://www.facebook.com/share/r/1AAbbC/"
OTHER_URL = "https://www.facebook.com/creator/posts/pfbid12345"


def origin():
    channel = SimpleNamespace(
        id=20, name="chat", is_nsfw=lambda: False,
    )
    msg = SimpleNamespace(
        id=10, guild=SimpleNamespace(id=30, name="Guild", filesize_limit=9_000_000),
        author=SimpleNamespace(
            id=50, display_name="User", bot=False,
            display_avatar=SimpleNamespace(url="https://cdn.example/avatar.png"),
        ),
        channel=channel,
        content=VIDEO_URL,
        nonce=None,
        jump_url="https://discord.com/channels/30/20/10",
        edit=AsyncMock(),
        reply=AsyncMock(),
    )
    channel.fetch_message = AsyncMock(return_value=msg)
    return msg


class FacebookURLTests(unittest.TestCase):
    def test_shared_video_keeps_original_route(self):
        for host in PROXY_DOMAINS["facebook"]:
            with self.subTest(host=host):
                output = build_proxy_url(VIDEO_URL, "facebook", host)
                self.assertIn("/share/v/1Ht6IiKfrP/", output)
                self.assertNotIn("/share/r/", output)
                self.assertTrue(output.startswith("https://" + host))
                self.assertIn("mibextid=wwXIfr", output)

    def test_reels_and_numeric_video_stay_stable(self):
        self.assertIn("/share/r/1AAbbC/", build_proxy_url(REEL_URL, "facebook", "facebed.com"))
        self.assertEqual(
            build_proxy_url("https://www.facebook.com/reel/123456", "facebook", "facebed.com"),
            "https://facebed.com/watch?v=123456",
        )

    def test_multiple_facebook_proxy_candidates(self):
        self.assertGreaterEqual(len(PROXY_DOMAINS["facebook"]), 4)
        self.assertEqual(len(set(PROXY_DOMAINS["facebook"])), len(PROXY_DOMAINS["facebook"]))
        self.assertEqual(PROXY_DOMAINS["facebook"][0], "facebed.com")
        self.assertTrue(any(p.search(VIDEO_URL) for p in PLATFORMS["facebook"]["patterns"]))


class FacebookValidatorTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def fake_session(html):
        class Response:
            status = 200
            url = "https://facebed.com/share/v/1Ht6IiKfrP/"
            headers = {"Content-Type": "text/html"}
            content = SimpleNamespace(read=AsyncMock(return_value=html.encode()))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                return False

        return SimpleNamespace(get=lambda *args, **kwargs: Response())

    async def test_reject_thumbnail_only_facebook_video(self):
        html = (
            '<meta property="og:title" content="Video from User">'
            '<meta property="og:description" content="Here is a video">'
            '<meta property="og:image" content="https://cdn.example/thumb.jpg">'
        )
        result = await validate_via_og_metadata(
            self.fake_session(html), "https://facebed.com/share/v/a", "facebook"
        )
        self.assertEqual(result, (False, False))

    async def test_accept_video_player_metadata(self):
        html = (
            '<meta property="og:title" content="Video from User">'
            '<meta property="og:video" content="https://cdn.example/video.mp4">'
        )
        result = await validate_via_og_metadata(
            self.fake_session(html), "https://facebed.com/share/v/a", "facebook"
        )
        self.assertEqual(result, (True, False))


class FacebookPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.bot = SimpleNamespace(config_manager=None, user=SimpleNamespace(id=99))
        self.cog = EmbedCog(self.bot)
        self.cog.session = object()
        self.msg = origin()
        self.bot.get_channel = lambda ident: self.msg.channel
        self.bot.fetch_channel = AsyncMock(return_value=self.msg.channel)

    async def test_proxy_success_never_invokes_ytdlp(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(
            status="success", tier="proxy", reason="proxy_link_sent", platform="facebook",
            proxy_domain="facebed.com", origin_message_id=10,
            preview_message_id=77,
        ))
        self.cog._try_ytdlp_fallback = AsyncMock()
        out = await self.cog._run_fallback_chain(
            self.msg, "facebook", VIDEO_URL, None, {}
        )
        self.assertTrue(out.success)
        self.cog._try_ytdlp_fallback.assert_not_awaited()

    async def test_ytdlp_is_last_resort_for_shared_video(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(
            reason="no_valid_proxy", platform="facebook",
        ))
        self.cog._try_ytdlp_fallback = AsyncMock(return_value=PreviewResult(
            "success", "ytdlp", "fallback_sent", "facebook",
            origin_message_id=10, preview_message_id=99, used_fallback=True,
        ))
        self.cog._offer_manual_fallback = AsyncMock()
        out = await self.cog._run_fallback_chain(
            self.msg, "facebook", VIDEO_URL, None, {}
        )
        self.assertTrue(out.success)
        self.assertEqual(out.tier, "ytdlp")
        self.assertEqual(out.fallback_reason, "no_valid_proxy")
        self.cog._offer_manual_fallback.assert_not_awaited()

    async def test_failed_final_fallback_shows_reason_and_link_button(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(
            reason="no_valid_proxy", platform="facebook",
        ))
        self.cog._try_ytdlp_fallback = AsyncMock(return_value=False)
        self.cog._send_embed_preview = AsyncMock(
            return_value=SimpleNamespace(id=74)
        )
        out = await self.cog._run_fallback_chain(
            self.msg, "facebook", VIDEO_URL, None, {}
        )
        self.assertEqual(out.status, "action_required")
        sent = self.cog._send_embed_preview.await_args.kwargs
        self.assertIn("Không lấy được preview video", sent["content"])
        self.assertNotIn("Preview lỗi?", sent["content"])
        self.assertTrue(any(
            isinstance(item, discord.ui.Button) and item.url == VIDEO_URL
            for item in sent["view"].children
        ))

    async def test_static_facebook_poster_is_not_ytdlp_video(self):
        self.cog._send_embed_preview = AsyncMock()
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=PostData(
            platform="facebook", media_type="image",
            media_urls=["https://cdn.example/poster.jpg"],
            text="Facebook video",
        ))):
            out = await self.cog._try_ytdlp_fallback(
                self.msg, "facebook", VIDEO_URL, {}
            )
        self.assertFalse(out)
        self.cog._send_embed_preview.assert_not_awaited()

    async def test_facebook_ytdlp_requires_downloaded_video(self):
        post = PostData(
            platform="facebook", media_type="video",
            media_urls=["https://cdn.example/video.mp4"],
            text="An actual user video",
        )
        self.cog._download_video_file = AsyncMock(return_value=None)
        self.cog._send_embed_preview = AsyncMock()
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=post)):
            out = await self.cog._try_ytdlp_fallback(
                self.msg, "facebook", VIDEO_URL, {}
            )
        self.assertFalse(out)
        self.cog._send_embed_preview.assert_not_awaited()

    async def test_photo_post_cannot_trigger_fb_ytdlp(self):
        self.cog._send_embed_preview = AsyncMock()
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock()) as fallback:
            self.assertFalse(await self.cog._try_ytdlp_fallback(
                self.msg, "facebook", OTHER_URL, {}
            ))
        fallback.assert_not_awaited()

    async def test_owner_reload_can_use_final_fallback_after_proxies(self):
        self.cog._try_ytdlp_fallback = AsyncMock(return_value=PreviewResult(
            "success", "ytdlp", "manual_fallback_sent", "facebook",
            origin_message_id=10, preview_message_id=75, used_fallback=True,
        ))
        self.cog._discard_preview = AsyncMock(return_value=True)
        old = SimpleNamespace(id=74, channel=self.msg.channel)
        payload = {
            "origin_id": 10, "channel_id": 20, "author_id": 50,
            "platform": "facebook", "url": VIDEO_URL, "tried_domains": [],
        }
        with patch("features.embed.cog.find_valid_proxy", new=AsyncMock(return_value=(None, False))):
            output = await self.cog.roll_facebook_proxy(payload, current_preview=old)
        self.assertTrue(output.success)
        self.cog._discard_preview.assert_awaited_once_with(10, old)

    async def test_no_preview_does_not_suppress_native_message(self):
        self.cog._process_url_with_fallback = AsyncMock(return_value=PreviewResult(
            status="action_required", tier="manual",
            reason="manual_fallback_offered", platform="facebook",
            origin_message_id=10, preview_message_id=70,
        ))
        with patch("features.embed.cog.EMBED_COOLDOWN") as bucket:
            bucket.get_bucket.return_value.update_rate_limit.return_value = None
            await self.cog.on_message(self.msg)
        self.msg.edit.assert_not_awaited()

    async def test_twitter_ytdlp_stays_enabled(self):
        self.cog._send_embed_preview = AsyncMock()
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=None)) as provider:
            await self.cog._try_ytdlp_fallback(
                self.msg, "twitter", "https://x.com/test/status/123", {}
            )
        provider.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
