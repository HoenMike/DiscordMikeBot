"""Safety and integration contracts for the opt-in social Components V2 pilot."""
import io
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from features.embed.builder import PostData, NSFWFilterResult
from features.embed.cog import EmbedCog, _preview_origin_header, _preview_presentation
from features.embed.native_v2 import build_native_social_layout, build_native_social_notice, can_render_native_social
from features.embed.result import PreviewResult
from features.embed.ui import EmbedActionView, EmbedActionLayoutView

URL = "https://bsky.app/profile/example.bsky.social/post/123"
JUMP = "https://discord.com/channels/30/20/10"


def post(media_type="image", media_urls=None):
    return PostData(
        platform="bluesky",
        author="Kitty @everyone **Bounce**",
        text="A cat in the barbershop @everyone",
        author_avatar="https://example.org/avatar.png",
        media_type=media_type,
        media_urls=media_urls if media_urls is not None else ["https://example.org/cat.jpg"],
        url=URL,
        likes=1220, comments=11, retweets=43,
    )


def origin():
    return SimpleNamespace(
        id=10,
        guild=SimpleNamespace(id=30, filesize_limit=25 * 1024 * 1024),
        channel=SimpleNamespace(id=20, is_nsfw=lambda: False),
        author=SimpleNamespace(id=50, display_name="Sender"),
        jump_url=JUMP,
        content=URL,
    )


def payload():
    return dict(
        origin_id=10, channel_id=20, author_id=50,
        platform="bluesky", url=URL, is_spoiler=False,
    )


class NativeSocialLayoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_compact_card_is_real_layout_with_media_and_owner_buttons(self):
        item = post()
        layout = build_native_social_layout(
            SimpleNamespace(), payload(), item, NSFWFilterResult(item),
            reply_url=JUMP, reply_author="Sender",
        )
        self.assertIsInstance(layout, discord.ui.LayoutView)
        self.assertIsInstance(layout, EmbedActionLayoutView)
        self.assertEqual(len(layout.children), 1)
        panel = layout.children[0]
        self.assertIsInstance(panel, discord.ui.Container)
        self.assertIsInstance(panel.children[1], discord.ui.Section)
        self.assertIsInstance(panel.children[1].accessory, discord.ui.Thumbnail)
        gallery = next(x for x in panel.children if isinstance(x, discord.ui.MediaGallery))
        self.assertEqual(len(gallery.items), 1)
        self.assertEqual(gallery.items[0].media.url, "https://example.org/cat.jpg")
        self.assertIsInstance(panel.children[-1], discord.ui.ActionRow)
        self.assertEqual(len(panel.children[-1].children), 2)
        contents = "\n".join(x.content for x in panel.children if isinstance(x, discord.ui.TextDisplay))
        self.assertIn("1.2K", contents)
        self.assertIn("11", contents)
        self.assertIn("43", contents)
        self.assertIn("[Xem bài gốc](" + URL + ")", contents)
        self.assertNotIn("@everyone", str(panel.to_component_dict()) if hasattr(panel, "to_component_dict") else contents)
        self.assertNotIn("**Bounce**", str(panel.children[1].children[0].content))
        self.assertEqual(_preview_origin_header(SimpleNamespace(
            content="", components=[panel],
        )).count(JUMP), 1)

        denied = SimpleNamespace(user=SimpleNamespace(id=999),
                                 response=SimpleNamespace(send_message=AsyncMock()))
        self.assertFalse(await layout.interaction_check(denied))
        denied.response.send_message.assert_awaited_once()

    async def test_unsupported_media_does_not_fake_playable_video(self):
        item = post("video", ["https://example.org/clip.mp4"])
        self.assertFalse(can_render_native_social(item, NSFWFilterResult(item), None))
        media = discord.File(io.BytesIO(b"video"), filename="clip.mp4")
        try:
            self.assertTrue(can_render_native_social(item, NSFWFilterResult(item), media))
            layout = build_native_social_layout(
                SimpleNamespace(), payload(), item, NSFWFilterResult(item),
                reply_url=JUMP, reply_author="Sender", file=media,
            )
            panel = layout.children[0]
            gallery = next(x for x in panel.children if isinstance(x, discord.ui.MediaGallery))
            self.assertEqual(gallery.items[0].media.url, "attachment://clip.mp4")
        finally:
            media.close()

    async def test_spoilers_require_attachment_and_never_expose_remote_media(self):
        item = post("image")
        spoiler = NSFWFilterResult(item, should_spoiler_media=True)
        self.assertFalse(can_render_native_social(item, spoiler, None))
        attached = discord.File(io.BytesIO(b"image"), filename="SPOILER_photo.png", spoiler=True)
        try:
            self.assertTrue(can_render_native_social(item, spoiler, attached))
            view = build_native_social_layout(
                SimpleNamespace(), payload(), item, spoiler,
                reply_url=JUMP, reply_author="Sender", file=attached,
            )
            panel = view.children[0]
            self.assertTrue(panel.spoiler)
            gallery = next(x for x in panel.children if isinstance(x, discord.ui.MediaGallery))
            self.assertEqual(gallery.items[0].media.url, "attachment://SPOILER_photo.png")
            self.assertTrue(gallery.items[0].spoiler)
            self.assertFalse(any(isinstance(x, discord.ui.Section) for x in panel.children))
        finally:
            attached.close()

    async def test_bad_image_urls_are_not_rendered(self):
        item = post("image", ["http://insecure.test/image.png", "https://example.org/x.png"])
        self.assertTrue(can_render_native_social(item, NSFWFilterResult(item), None))
        item.media_urls = ["http://insecure.test/image.png"]
        self.assertFalse(can_render_native_social(item, NSFWFilterResult(item), None))
        item.media_urls = ["https://example.org/hi)there.jpg"]
        self.assertFalse(can_render_native_social(item, NSFWFilterResult(item), None))

    async def test_text_only_social_post_uses_compact_v2_without_fake_gallery(self):
        item = post("text", [])
        decision = NSFWFilterResult(item)
        self.assertTrue(can_render_native_social(item, decision, None))
        layout = build_native_social_layout(
            SimpleNamespace(), payload(), item, decision,
            reply_url=JUMP, reply_author="Sender",
        )
        panel = layout.children[0]
        self.assertIsInstance(panel, discord.ui.Container)
        self.assertFalse(any(isinstance(x, discord.ui.MediaGallery) for x in panel.children))
        self.assertIsInstance(panel.children[-1], discord.ui.ActionRow)
        text = "\\n".join(
            x.content for x in panel.children if isinstance(x, discord.ui.TextDisplay)
        )
        self.assertIn("Xem bài gốc", text)
        self.assertIn("1.2K", text)

    async def test_never_create_empty_or_fake_text_cards(self):
        item = post("text", [])
        item.text = ""
        self.assertFalse(can_render_native_social(item, NSFWFilterResult(item), None))
        item.text = "genuine public note"
        item.url = "http://not-secure.example/test"
        self.assertFalse(can_render_native_social(item, NSFWFilterResult(item), None))

    async def test_v2_image_gallery_text_matrix_for_supported_social_sites(self):
        # Structured fetcher content is handled consistently regardless of
        # which supported platform produced it. Video-proxy paths are separate.
        for name in ("twitter", "reddit", "tiktok", "bluesky", "pixiv", "threads"):
            for kind, urls in (
                ("text", []), ("image", ["https://example.org/img.png"]),
                ("gallery", ["https://example.org/1.png", "https://example.org/2.png"]),
            ):
                with self.subTest(platform=name, media=kind):
                    item = post(kind, urls)
                    item.platform = name
                    self.assertTrue(can_render_native_social(item, NSFWFilterResult(item), None))
                    layout = build_native_social_layout(
                        SimpleNamespace(), payload(), item, NSFWFilterResult(item),
                        reply_url=JUMP, reply_author="Sender",
                    )
                    self.assertIsInstance(layout.children[0], discord.ui.Container)
                    self.assertIsInstance(layout.children[0].children[-1], discord.ui.ActionRow)

    async def test_compact_notice_has_no_video_thumbnail_or_proxy_unfurl(self):
        layout = build_native_social_notice(
            SimpleNamespace(), {**payload(), "platform": "facebook"},
            reply_url=JUMP, reply_author="Sender",
            platform="facebook", hint="Không lấy được video, chọn đổi nguồn",
        )
        self.assertIsInstance(layout, discord.ui.LayoutView)
        self.assertFalse(any(
            isinstance(x, discord.ui.MediaGallery) for x in layout.children[0].children
        ))
        self.assertIsInstance(layout.children[0].children[-1], discord.ui.ActionRow)

    async def test_legacy_view_remains_available_for_facebook_proxy(self):
        legacy = EmbedActionView(SimpleNamespace(), {
            **payload(), "platform": "facebook",
        })
        self.assertNotIsInstance(legacy, discord.ui.LayoutView)
        self.assertEqual(legacy.reload_button.label, "Đổi nguồn")


class NativeSocialPipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cog = EmbedCog(MagicMock())
        self.cog.session = object()
        self.msg = origin()
        self.config = {"nsfw_mode": "spoiler"}

    async def test_api_image_v2_send_has_no_content_or_embeds(self):
        item = post()
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=501))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}), \
             patch.dict("features.embed.cog.FETCHER_MAP", {"bluesky": AsyncMock(return_value=item)}):
            result = await self.cog._try_api_fetcher(self.msg, "bluesky", URL, None, self.config)
        self.assertTrue(result.success)
        kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertNotIn("content", kwargs)
        self.assertNotIn("embeds", kwargs)
        self.assertEqual(result.reason, "api_v2_preview_sent")

    async def test_explicit_v2_rejection_downgrades_image_to_legacy_once(self):
        item = post()
        self.cog._send_embed_preview = AsyncMock(
            side_effect=[None, SimpleNamespace(id=502)],
        )
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}), \
             patch.dict("features.embed.cog.FETCHER_MAP", {"bluesky": AsyncMock(return_value=item)}):
            result = await self.cog._try_api_fetcher(self.msg, "bluesky", URL, None, self.config)
        self.assertEqual(result.reason, "api_preview_sent")
        self.assertEqual(self.cog._send_embed_preview.await_count, 2)
        self.assertIsInstance(self.cog._send_embed_preview.await_args.kwargs["view"], discord.ui.View)
        self.assertNotIsInstance(self.cog._send_embed_preview.await_args.kwargs["view"], discord.ui.LayoutView)

    async def test_disabled_v2_uses_legacy(self):
        item = post()
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=503))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "false"}), \
             patch.dict("features.embed.cog.FETCHER_MAP", {"bluesky": AsyncMock(return_value=item)}):
            await self.cog._try_api_fetcher(self.msg, "bluesky", URL, None, self.config)
        kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIn("embeds", kwargs)
        self.assertIn("content", kwargs)

    async def test_failed_video_v2_does_not_reuse_closed_attachment(self):
        item = post("video", ["https://example.org/clip.mp4"])
        self.cog._send_embed_preview = AsyncMock(return_value=None)
        downloaded = discord.File(io.BytesIO(b"video"), filename="clip.mp4")
        self.cog._download_video_file = AsyncMock(return_value=downloaded)
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}), \
             patch.dict("features.embed.cog.FETCHER_MAP", {"bluesky": AsyncMock(return_value=item)}):
            outcome = await self.cog._try_api_fetcher(self.msg, "bluesky", URL, None, self.config)
        self.assertFalse(outcome)
        self.assertEqual(self.cog._send_embed_preview.await_count, 1)
        downloaded.close()

    async def test_text_only_api_uses_v2_instead_of_legacy(self):
        item = post("text", [])
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=601))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}), \\
             patch.dict("features.embed.cog.FETCHER_MAP", {"bluesky": AsyncMock(return_value=item)}):
            result = await self.cog._try_api_fetcher(self.msg, "bluesky", URL, None, self.config)
        self.assertEqual(result.reason, "api_v2_preview_sent")
        kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertNotIn("embeds", kwargs)
        self.assertNotIn("content", kwargs)

    async def test_unavailable_facebook_player_uses_v2_notice_not_fake_video(self):
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=602))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}):
            result = await self.cog._offer_manual_fallback(
                self.msg, "facebook", "https://www.facebook.com/share/v/123/",
                reason="no_proxy_sources",
            )
        self.assertEqual(result.reason, "manual_fallback_v2_offered")
        kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertNotIn("content", kwargs)
        self.assertEqual(_preview_presentation(result), "components_v2")

    async def test_emergency_disable_restores_legacy_notice(self):
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=603))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "false"}):
            result = await self.cog._offer_manual_fallback(
                self.msg, "facebook", "https://www.facebook.com/share/v/123/",
                reason="no_proxy_sources",
            )
        self.assertEqual(result.reason, "manual_fallback_offered")
        kwargs = self.cog._send_embed_preview.await_args.kwargs
        self.assertIn("content", kwargs)
        self.assertNotIsInstance(kwargs["view"], discord.ui.LayoutView)
        self.assertEqual(_preview_presentation(result), "legacy")

    async def test_platform_presentation_reports_native_proxy_without_claiming_v2(self):
        proxy = PreviewResult(
            "success", "proxy", "proxy_sent_user_controlled", "facebook",
            origin_message_id=10, preview_message_id=504,
        )
        self.assertEqual(_preview_presentation(proxy), "native_proxy_player")
        self.assertEqual(_preview_presentation(PreviewResult(
            "success", "api", "api_v2_preview_sent", "bluesky",
            origin_message_id=10, preview_message_id=505,
        )), "components_v2")

    async def test_facebook_proxy_never_changes_to_v2_even_with_flag(self):
        self.cog.config_manager = None
        self.cog._send_embed_preview = AsyncMock(return_value=SimpleNamespace(id=504))
        with patch.dict("os.environ", {"ASUMI_SOCIAL_NATIVE_V2_ENABLED": "true"}), \
             patch("features.embed.cog.validate_via_og_metadata", new=AsyncMock(return_value=(False, False))):
            result = await self.cog._try_proxy_chain(
                self.msg, "facebook", "https://www.facebook.com/share/r/123/", self.config,
            )
        self.assertTrue(result.success)
        kw = self.cog._send_embed_preview.await_args.kwargs
        self.assertIn("content", kw)
        self.assertIsInstance(kw["view"], EmbedActionView)
        self.assertNotIsInstance(kw["view"], discord.ui.LayoutView)


if __name__ == "__main__":
    unittest.main()
