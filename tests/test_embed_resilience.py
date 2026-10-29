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
from features.embed.facebook_urls import resolve_facebook_share_video, _trusted_facebook_url


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


class FacebookShortLinkResolutionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def session_for(*responses):
        class Response:
            def __init__(self, status, location="", html=""):
                self.status = status
                self.headers = (
                    {"Location": location} if location else
                    {"Content-Type": "text/html"}
                )
                self.content = SimpleNamespace(read=AsyncMock(return_value=html.encode()))

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        entries = iter([Response(*entry) for entry in responses])
        return SimpleNamespace(get=lambda *args, **kwargs: next(entries))

    async def test_short_reel_redirects_to_numeric_video_without_login(self):
        session = self.session_for(
            (302, "https://www.facebook.com/reel/123456789/")
        )
        result = await resolve_facebook_share_video(
            session, "https://www.facebook.com/share/r/1KfknmPddc/"
        )
        self.assertEqual(result, "https://www.facebook.com/reel/123456789/")

    async def test_short_video_metadata_can_provide_numeric_reel(self):
        session = self.session_for((
            200, "", '<meta property="og:url" content="https://www.facebook.com/reel/9876543/">'
        ))
        result = await resolve_facebook_share_video(
            session, "https://www.facebook.com/share/v/ABCDE/"
        )
        self.assertEqual(result, "https://www.facebook.com/reel/9876543/")

    async def test_login_redirect_and_external_redirect_never_get_followed(self):
        for location in (
            "https://www.facebook.com/login.php?next=%2Freel%2F1234",
            "https://evil.example/private",
            "http://127.0.0.1/",
            "//evil.example/x",
        ):
            with self.subTest(location=location):
                session = self.session_for((302, location))
                self.assertIsNone(await resolve_facebook_share_video(
                    session, "https://www.facebook.com/share/r/1KfknmPddc/"
                ))

    async def test_generic_login_page_never_resolves_to_player(self):
        session = self.session_for((
            200, "", '<meta property="og:title" content="Log in or sign up to view">'
        ))
        self.assertIsNone(await resolve_facebook_share_video(
            session, "https://www.facebook.com/share/r/1KfknmPddc/"
        ))

    async def test_untrusted_host_cannot_be_fetched(self):
        s = SimpleNamespace(get=AsyncMock())
        for url in (
            "http://www.facebook.com/share/r/123/",
            "https://facebook.com.evil.test/share/r/123/",
            "https://user:secret@facebook.com/share/r/123/",
            "https://facebook.com:8443/share/r/123/",
        ):
            self.assertFalse(_trusted_facebook_url(url))
            self.assertIsNone(await resolve_facebook_share_video(s, url))
        s.get.assert_not_awaited()


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

    async def test_facebook_video_does_not_auto_download_when_proxy_fails(self):
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(
            reason="no_proxy_sources", platform="facebook",
        ))
        self.cog._try_ytdlp_fallback = AsyncMock()
        self.cog._offer_manual_fallback = AsyncMock(return_value=PreviewResult(
            "action_required", "manual", "manual_fallback_offered", "facebook",
            origin_message_id=10,
        ))
        out = await self.cog._run_fallback_chain(self.msg, "facebook", VIDEO_URL, None, {})
        self.assertEqual(out.status, "action_required")
        self.cog._try_ytdlp_fallback.assert_not_awaited()
        self.cog._offer_manual_fallback.assert_awaited_once()
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
        self.assertIn("Chưa lấy được video Reel", sent["content"])
        self.assertNotIn("Preview lỗi?", sent["content"])
        self.assertEqual(len(sent["view"].children), 2)
        self.assertFalse(any(
            isinstance(item, discord.ui.Button) and item.url
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

    async def test_manual_roll_on_notice_edits_notice_to_first_proxy(self):
        old = SimpleNamespace(id=74, channel=self.msg.channel, content="Chưa lấy được video",
                              edit=AsyncMock())
        payload = {
            "origin_id": 10, "channel_id": 20, "author_id": 50,
            "platform": "facebook", "url": VIDEO_URL,
        }
        self.cog._try_ytdlp_fallback = AsyncMock()
        self.cog._send_embed_preview = AsyncMock()
        self.cog._discard_preview = AsyncMock()
        with patch("features.embed.cog.resolve_facebook_share_video", new=AsyncMock(return_value=None)), patch(
            "features.embed.cog.validate_via_og_metadata", new=AsyncMock(return_value=(False, False)),
        ):
            out = await self.cog.roll_facebook_proxy(payload, current_preview=old)
        self.assertTrue(out.success)
        self.assertEqual(out.preview_message_id, 74)
        self.assertEqual(out.proxy_domain, "facebed.com")
        old.edit.assert_awaited_once()
        self.cog._try_ytdlp_fallback.assert_not_awaited()
        self.cog._send_embed_preview.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()
    async def test_no_preview_does_not_suppress_native_message(self):
        self.cog._process_url_with_fallback = AsyncMock(return_value=PreviewResult(
            status="action_required", tier="manual",
            reason="manual_fallback_offered", platform="facebook",
            origin_message_id=10, preview_message_id=70,
        ))
        with patch("features.embed.cog.EMBED_COOLDOWN") as bucket, \
             patch("core.activity_logger.activity_logger.log"):
            # Unit tests must not spawn a real DB persist task: its libsql
            # executor can outlive IsolatedAsyncioTestCase and hang CI shutdown.
            bucket.get_bucket.return_value.update_rate_limit.return_value = None
            await self.cog.on_message(self.msg)
        self.msg.edit.assert_not_awaited()

    async def test_facebook_video_requires_a_playable_unfurl(self):
        """A login prompt or attractive thumbnail is not a Reel player."""
        login = discord.Embed(title="Log in or sign up to view",
                              description="See posts, photos and more on Facebook.")
        poster = discord.Embed(title="Max Verstappen driving", description="Watch video")
        poster.set_image(url="https://cdn.example/frame.jpg")
        video = SimpleNamespace(
            title="Real video", description="", url="", type="video",
            video=SimpleNamespace(url="https://cdn.example/video.mp4"),
            image=SimpleNamespace(url=None), thumbnail=SimpleNamespace(url=None),
        )
        preview = SimpleNamespace(id=80, channel=self.msg.channel)
        for candidate, ok in [(login, False), (poster, False), (video, True)]:
            with self.subTest(card=candidate.title), patch(
                "features.embed.cog._UNFURL_DELAYS", (0,)
            ):
                self.msg.channel.fetch_message = AsyncMock(
                    return_value=SimpleNamespace(embeds=[candidate])
                )
                result, _ = await self.cog._verify_proxy_unfurl(
                    10, preview, "facebook", require_video=True
                )
                self.assertEqual(result, ok)

    async def test_false_negative_unfurl_never_triggers_automatic_fallback(self):
        proxy = "https://www.facebook.com/share/v/199BjfPzAj/"
        preview = SimpleNamespace(id=81)
        self.cog._send_embed_preview = AsyncMock(return_value=preview)
        self.cog._verify_proxy_unfurl = AsyncMock(return_value=(False, "unfurl_timeout"))
        self.cog._discard_preview = AsyncMock()
        with patch("features.embed.cog.validate_via_og_metadata",
                   new=AsyncMock(return_value=(False, False))):
            out = await self.cog._try_proxy_chain(self.msg, "facebook", proxy, {})
        self.assertTrue(out.success)
        self.assertFalse(out.unfurl_verified)
        self.assertEqual(out.proxy_domain, "facebed.com")
        self.assertEqual(out.preview_message_id, 81)
        self.cog._verify_proxy_unfurl.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()
        self.cog._send_embed_preview.assert_awaited_once()
        self.assertEqual(self.cog._facebook_current_domain[(10, proxy)], "facebed.com")
    async def test_manual_edit_failure_keeps_original_preview_and_state(self):
        old = SimpleNamespace(
            id=70, channel=self.msg.channel,
            content="[facebed.com](https://facebed.com/share/v/1Ht6IiKfrP/)",
            edit=AsyncMock(side_effect=discord.Forbidden(
                SimpleNamespace(status=403, reason="forbidden"), "forbidden",
            )),
        )
        payload = {
            "origin_id": 10, "channel_id": 20, "author_id": 50,
            "platform": "facebook", "url": VIDEO_URL, "current_domain": "facebed.com",
        }
        self.cog._facebook_current_domain[(10, VIDEO_URL)] = "facebed.com"
        self.cog._send_embed_preview = AsyncMock()
        self.cog._discard_preview = AsyncMock()
        self.cog._try_ytdlp_fallback = AsyncMock()
        with patch("features.embed.cog.resolve_facebook_share_video", new=AsyncMock(return_value=None)), patch(
            "features.embed.cog.validate_via_og_metadata", new=AsyncMock(return_value=(False, False)),
        ):
            out = await self.cog.roll_facebook_proxy(payload, current_preview=old)
        self.assertFalse(out.success)
        self.assertEqual(out.reason, "proxy_edit_unavailable")
        self.assertEqual(self.cog._facebook_current_domain[(10, VIDEO_URL)], "facebed.com")
        self.cog._send_embed_preview.assert_not_awaited()
        self.cog._discard_preview.assert_not_awaited()
        self.cog._try_ytdlp_fallback.assert_not_awaited()
    async def test_facebook_share_keeps_canonical_url_for_proxy_only(self):
        canonical = "https://www.facebook.com/reel/123456789/"
        self.cog._try_api_fetcher = AsyncMock(return_value=False)
        self.cog._try_proxy_chain = AsyncMock(return_value=PreviewResult(
            reason="no_proxy_sources", platform="facebook",
        ))
        self.cog._try_ytdlp_fallback = AsyncMock()
        self.cog._offer_manual_fallback = AsyncMock(return_value=PreviewResult(
            "action_required", "manual", "manual_fallback_offered", "facebook",
        ))
        with patch("features.embed.cog.resolve_facebook_share_video",
                   new=AsyncMock(return_value=canonical)) as resolver:
            out = await self.cog._run_fallback_chain(
                self.msg, "facebook", "https://www.facebook.com/share/r/1KfknmPddc/",
                None, {},
            )
        self.assertEqual(out.status, "action_required")
        resolver.assert_awaited_once()
        self.assertEqual(self.cog._try_proxy_chain.await_args.kwargs["lookup_url"], canonical)
        self.cog._try_ytdlp_fallback.assert_not_awaited()
    async def test_twitter_ytdlp_stays_enabled(self):
        self.cog._send_embed_preview = AsyncMock()
        with patch("features.embed.cog.extract_media_ytdlp", new=AsyncMock(return_value=None)) as provider:
            await self.cog._try_ytdlp_fallback(
                self.msg, "twitter", "https://x.com/test/status/123", {}
            )
        provider.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
