"""Codex Watch hotfix: server manager, Discord app owner, denied commands."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from discord import app_commands

from features.codex_watch.cog import can_manage_codex_watch, reply_ephemeral
from core.app_command_errors import app_error_message, reply_app_error


def mock_interaction(*, manager=False, guild_owner=False, application_owner=False,
                     already_deferred=False):
    user = SimpleNamespace(id=101, guild_permissions=SimpleNamespace(manage_guild=manager))
    guild = SimpleNamespace(id=500, owner_id=101 if guild_owner else 999)
    response = SimpleNamespace(
        is_done=Mock(return_value=already_deferred),
        defer=AsyncMock(),
        send_message=AsyncMock(),
    )
    followup = SimpleNamespace(send=AsyncMock())
    client = SimpleNamespace(is_owner=AsyncMock(return_value=application_owner))
    return SimpleNamespace(
        user=user, guild=guild, response=response, followup=followup, client=client,
    )


class CodexWatchAuthorizationTest(unittest.IsolatedAsyncioTestCase):
    async def test_server_manager_allowed_without_owner_lookup_or_defer(self):
        i = mock_interaction(manager=True)
        self.assertTrue(await can_manage_codex_watch(i))
        i.client.is_owner.assert_not_awaited()
        i.response.defer.assert_not_awaited()

    async def test_guild_owner_allowed_without_api_call(self):
        i = mock_interaction(guild_owner=True)
        self.assertTrue(await can_manage_codex_watch(i))
        i.client.is_owner.assert_not_awaited()

    async def test_verified_discord_application_owner_can_configure(self):
        i = mock_interaction(application_owner=True)
        self.assertTrue(await can_manage_codex_watch(i))
        i.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        i.client.is_owner.assert_awaited_once_with(i.user)

    async def test_nonowner_denied_with_explicit_reason(self):
        i = mock_interaction()
        with self.assertRaisesRegex(app_commands.CheckFailure, "Manage Server"):
            await can_manage_codex_watch(i)
        i.client.is_owner.assert_awaited_once()
        i.response.defer.assert_awaited_once()

    async def test_owner_lookup_failure_denies_without_bypass(self):
        i = mock_interaction()
        i.client.is_owner.side_effect = OSError("service unavailable")
        with self.assertRaisesRegex(app_commands.CheckFailure, "Không xác minh"):
            await can_manage_codex_watch(i)

    async def test_followup_used_after_owner_check_defer(self):
        i = mock_interaction(already_deferred=True)
        await reply_ephemeral(i, "OK", allowed_mentions=None)
        i.followup.send.assert_awaited_once_with(
            "OK", ephemeral=True, allowed_mentions=None,
        )
        i.response.send_message.assert_not_awaited()

    async def test_initial_response_without_defer(self):
        i = mock_interaction()
        await reply_ephemeral(i, "OK")
        i.response.send_message.assert_awaited_once_with("OK", ephemeral=True)


class AppCommandErrorHandlingTest(unittest.IsolatedAsyncioTestCase):
    async def test_missing_server_permission_gets_ephemeral_reply(self):
        i = mock_interaction()
        err = app_commands.MissingPermissions(["manage_guild"])
        self.assertIn("manage_guild", app_error_message(err))
        await reply_app_error(i, err)
        args, kwargs = i.response.send_message.await_args
        self.assertIn("manage_guild", args[0])
        self.assertTrue(kwargs["ephemeral"])
        self.assertFalse(kwargs["allowed_mentions"].roles)

    async def test_custom_permission_failure_after_defer(self):
        i = mock_interaction(already_deferred=True)
        await reply_app_error(
            i, app_commands.CheckFailure("Bạn không có quyền cấu hình Watch."),
        )
        i.followup.send.assert_awaited_once()
        self.assertIn("không có quyền", i.followup.send.await_args.args[0])

    async def test_unknown_errors_are_replied_generically(self):
        i = mock_interaction()
        await reply_app_error(i, app_commands.AppCommandError("internal details"))
        self.assertNotIn("internal details", i.response.send_message.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
