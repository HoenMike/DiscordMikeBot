"""Regression for safe, bounded deploy catch-up; no real Discord calls."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

from core.deploy_recovery import (
    DeployRecovery, RECOVERY_ACK, already_answered, eligible_replay,
)


def msg(text="<@99> giải thích tin nhắn này", msg_id=44):
    return NS(
        id=msg_id, content=text,
        guild=NS(id=11), channel=NS(id=22),
        author=NS(id=30, bot=False),
        created_at=datetime.now(timezone.utc),
    )


class RecoveryGates(unittest.TestCase):
    def test_explicit_mention_only_and_no_unsafe_command_replay(self):
        self.assertTrue(eligible_replay(msg(), 99))
        for text in (
            "giải thích chat này", "<@12> giải thích chat",
            "<@99> /tarot", "<@99> .m delete", "<@99> !admin",
            "<@99> feedback lỗi search", "<@99> báo lỗi Asumi",
            "<@99> /feedback", "<@99> ",
        ):
            with self.subTest(text=text):
                self.assertFalse(eligible_replay(msg(text), 99))
        message = msg()
        message.guild = None
        self.assertFalse(eligible_replay(message, 99))
        message = msg()
        message.author.bot = True
        self.assertFalse(eligible_replay(message, 99))

    def test_existing_bot_reply_is_not_repeated_except_progress_ack(self):
        message = msg()
        def response(content):
            return NS(
                author=NS(id=99),
                reference=NS(message_id=message.id),
                content=content,
            )
        self.assertTrue(already_answered(message, [response("Đã giải thích")], 99))
        self.assertFalse(already_answered(message, [response(RECOVERY_ACK)], 99))
        self.assertFalse(already_answered(message, [response("Đã giải thích")], 101))


class RecoveryStore(unittest.IsolatedAsyncioTestCase):
    async def test_claim_is_compare_and_swap_with_retry_cap(self):
        store = NS(commit=AsyncMock(), execute=AsyncMock(return_value=NS(rowcount=1)))
        recovery = DeployRecovery(store=store)
        token = await recovery.claim(42)
        self.assertIsInstance(token, str)
        self.assertEqual(len(token), 32)
        query, args = store.execute.await_args.args
        self.assertIn("attempts<?", query)
        self.assertIn("status='processing'", query)
        self.assertIn("claim_token=?", query)
        self.assertEqual(args[0], token)
        self.assertEqual(args[2], "42")
        self.assertEqual(args[3], 2)

        await recovery.finish(42, done=True, claim_token=token)
        finish_query, finish_args = store.execute.await_args.args
        self.assertIn("claim_token=?", finish_query)
        self.assertIn("status='processing'", finish_query)
        self.assertEqual(finish_args[-1], token)

        store.execute.return_value = NS(rowcount=0)
        self.assertIsNone(await recovery.claim(42))

    async def test_local_sqlite_cannot_claim_durable_guarantee(self):
        store = NS(is_cloud=False, connect=AsyncMock(), execute=AsyncMock())
        recovery = DeployRecovery(store=store)
        self.assertFalse(await recovery.register(msg()))
        store.execute.assert_not_awaited()

    async def test_register_uses_message_ids_never_saves_raw_chat(self):
        store = NS(
            is_cloud=True, connect=AsyncMock(), commit=AsyncMock(),
            execute=AsyncMock(return_value=NS(rowcount=1)),
        )
        recovery = DeployRecovery(store=store)
        request = msg("<@99> bí mật riêng tư 123")
        self.assertTrue(await recovery.register(request))
        # Schema creation and one insert. Only IDs/timestamps leave this process.
        insert = [c for c in store.execute.await_args_list
                  if "INSERT OR IGNORE" in c.args[0]][0]
        self.assertEqual(insert.args[1][0], str(request.id))
        self.assertNotIn("bí mật", str(insert.args))

    async def test_inflight_lease_gets_visible_status_without_double_execution(self):
        class FakeMember:
            id = 30
            bot = False

        user = FakeMember()
        perms = NS(view_channel=True)
        channel = NS(permissions_for=lambda *_: perms)
        request = msg()
        request.author = user
        request.channel = channel
        request.reply = AsyncMock()
        bot = NS(user=NS(id=99))
        recovery = DeployRecovery()
        recovery._can_read = lambda *args: True
        recovery.register = AsyncMock(return_value=True)
        recovery.claim = AsyncMock(return_value=None)
        recovery.status = AsyncMock(return_value="processing")
        with patch("core.deploy_recovery.discord.Member", FakeMember):
            await recovery._replay(bot, request, [])
        request.reply.assert_awaited_once()
        self.assertIn("kết nối lại", request.reply.await_args.args[0])
        recovery.status.assert_awaited_once_with(request.id)

    async def test_replay_delivers_once_and_cleans_up_progress(self):
        class FakeMember:
            id = 30
            bot = False

        user = FakeMember()
        channel = NS(permissions_for=lambda *_: NS(view_channel=True))
        request = msg()
        request.author = user
        request.channel = channel
        ack = NS(delete=AsyncMock())
        request.reply = AsyncMock(return_value=ack)
        assistant = NS(handle_conversation_message=AsyncMock(return_value=True))
        bot = NS(user=NS(id=99), get_cog=lambda name: assistant)
        recovery = DeployRecovery()
        recovery._can_read = lambda *args: True
        recovery.register = AsyncMock(return_value=True)
        recovery.claim = AsyncMock(return_value="claim-1")
        recovery.finish = AsyncMock()
        with patch("core.deploy_recovery.discord.Member", FakeMember):
            await recovery._replay(bot, request, [])
        assistant.handle_conversation_message.assert_awaited_once_with(
            request, recovery_mode=True,
        )
        recovery.finish.assert_awaited_once_with(
            request.id, done=True, claim_token="claim-1",
        )
        ack.delete.assert_awaited_once()

    async def test_recovery_skips_unsafe_but_finds_eligible_mention(self):
        text = NS(
            view_channel=True, read_message_history=True, send_messages=True
        )
        channel = NS(
            id=22, guild=NS(me=object()),
            permissions_for=lambda *_: text,
        )
        entries = [
            msg("<@99> giải thích cái ảnh này", 11),
            msg("<@99> /tarot", 12),
            msg("tin bình thường", 13),
        ]
        async def history(*, limit, after, oldest_first):
            self.assertLessEqual(limit, 100)
            self.assertFalse(oldest_first)
            for m in reversed(entries):
                m.channel = channel
                yield m
        channel.history = history
        guild = NS(text_channels=[channel], threads=[])
        bot = NS(guilds=[guild], user=NS(id=99))
        recovery = DeployRecovery()
        recovery._replay = AsyncMock()
        processed = await recovery.recover(bot, cutoff=0)
        self.assertEqual(processed, 1)
        self.assertEqual(recovery._replay.await_args.args[1].id, 11)


if __name__ == "__main__":
    unittest.main()
