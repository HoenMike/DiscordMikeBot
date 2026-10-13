"""Discord send guards: no onebox, no accidental role ping, explicit opt-in."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from features.codex_watch.cog import CodexWatch, parse_independent_forecast
from features.codex_watch.store import WatchConfig


class CodexDiscordSendTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cfg = WatchConfig(101, 102, 103, True,
                               datetime(2026, 10, 13, tzinfo=timezone.utc))
        self.role = SimpleNamespace(id=103)
        self.channel = SimpleNamespace(id=102, send=AsyncMock(
            return_value=SimpleNamespace(id=999)))
        guild = Mock()
        guild.get_channel.return_value = self.channel
        guild.get_role.return_value = self.role
        bot = Mock()
        bot.get_guild.return_value = guild
        self.cog = CodexWatch(bot)
        self.cog._permitted = Mock(return_value=True)

    async def test_sent_alert_only_mentions_configured_role_and_suppresses_embed(self):
        with patch("features.codex_watch.cog.codex_watch_store") as store, \
             patch("features.codex_watch.cog.discord.TextChannel", type(self.channel)):
            store.get = AsyncMock(return_value=self.cfg)
            store.claim = AsyncMock(return_value=True)
            store.complete = AsyncMock()
            await self.cog._send(self.cfg, "tibo:2026-10-13:banked", "https://example.org",
                                 "🟣 **CODEX BANKED RESET**\n<https://x.com/thsottiaux/status/1234567890123456789>")
        self.channel.send.assert_awaited_once()
        args, kwargs = self.channel.send.await_args
        self.assertTrue(kwargs["suppress_embeds"])
        self.assertTrue(args[0].startswith("<@&103>"))
        allowed = kwargs["allowed_mentions"]
        self.assertFalse(allowed.everyone)
        self.assertFalse(allowed.users)
        self.assertEqual([self.role], allowed.roles)

    async def test_reconfiguration_during_poll_aborts_send(self):
        with patch("features.codex_watch.cog.codex_watch_store") as store, \
             patch("features.codex_watch.cog.discord.TextChannel", type(self.channel)):
            store.get = AsyncMock(return_value=WatchConfig(101, 999, 103, True,
                                 datetime(2026,10,13,tzinfo=timezone.utc)))
            store.claim = AsyncMock()
            await self.cog._send(self.cfg, "key", "https://example.org", "test")
        self.channel.send.assert_not_awaited()
        store.claim.assert_not_awaited()


class ForecastSafetyTest(unittest.TestCase):
    def test_requires_independent_model_timestamp_and_percentages(self):
        now = datetime(2026, 10, 13, 5, 0, tzinfo=timezone.utc)
        markup = (
            "<h1>Codex Observatory</h1><p>Within 24h 87%</p>"
            "<p>Within 48h 94%</p><p>Last updated: Oct 13, 2026, 12:17 PM JST</p>"
        )
        self.assertEqual((87,94), parse_independent_forecast(markup, now))
        self.assertIsNone(parse_independent_forecast(
            markup.replace("Oct 13", "Oct 10"), now
        ))
        self.assertIsNone(parse_independent_forecast(
            "Within 24h 87% Within 48h 94%", now
        ))


if __name__ == "__main__":
    unittest.main()
