"""
features/cabin/cog.py - Cog điều khiển Slash Command, Prefix Command và Listener cho tính năng Dịch Cabin AI.
"""

import asyncio
import sys
import time
import traceback
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands, tasks

from core.activity_logger import activity_logger
from features.cabin.ai import generate_cabin_interpretation, generate_cabin_interpretation_batch
from features.cabin.constants import (
    CABIN_EMBED_COLOR,
    CONTEXT_HISTORY_MINUTES,
    CONTEXT_MAX_MESSAGES,
    DEFAULT_DURATION_SECONDS,
    format_duration,
    parse_duration,
)
from features.cabin.manager import cabin_manager


class CabinStopView(discord.ui.View):
    """View tương tác chứa nút Dừng Cabin 1-chạm."""

    def __init__(self, guild_id: int, target_id: int, creator_id: int, timeout: Optional[float] = 10800):
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.target_id = target_id
        self.creator_id = creator_id

    @discord.ui.button(label="Dừng Cabin", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user

        # Kiểm tra quyền: Nạn nhân, Người tạo ban đầu, Người điều khiển hiện tại (nếu bị đè quyền), hoặc Quản trị viên
        is_target = (user.id == self.target_id)
        session = cabin_manager.get_session(self.guild_id, self.target_id)
        is_creator = (user.id == self.creator_id) or (session and user.id == session.creator_id)
        is_admin = False
        if isinstance(user, discord.Member):
            is_admin = user.guild_permissions.manage_messages or user.guild_permissions.administrator

        if not (is_target or is_creator or is_admin):
            await interaction.response.send_message(
                "⛔ **Bạn không có quyền dừng phiên cabin này!** Chỉ nạn nhân, người bật hoặc Quản trị viên mới có thể bấm dừng.",
                ephemeral=True
            )
            return

        # Thực hiện dừng session
        stopped = await cabin_manager.stop_session(self.guild_id, self.target_id)
        button.disabled = True
        button.label = "Đã Dừng Cabin"

        if stopped:
            stop_embed = discord.Embed(
                title="🛑 ĐÃ DỪNG CHẾ ĐỘ DỊCH CABIN",
                description=(
                    f"Phiên Dịch Cabin cho <@{self.target_id}> đã được dừng bởi {user.mention}.\n"
                    f"🕊️ Thành viên này giờ đã có thể thoải mái trò chuyện bình thường!"
                ),
                color=0x95A5A6
            )
            await interaction.response.edit_message(embed=stop_embed, view=self)
        else:
            await interaction.response.edit_message(
                content="ℹ️ Phiên Dịch Cabin này đã kết thúc hoặc không còn tồn tại.",
                view=self
            )


class CabinCog(commands.Cog, name="Cabin"):
    """Cog xử lý toàn bộ logic tính năng Dịch Cabin AI troll trực tiếp."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cleanup_task.start()
        # Debounce buffers: (guild_id, author_id) -> list of (text, discord.Message)
        self._msg_buffers: Dict = defaultdict(list)
        # Debounce tasks: (guild_id, author_id) -> asyncio.Task
        self._debounce_tasks: Dict = {}

    async def cog_load(self):
        """Khởi tạo database khi nạp Cog."""
        try:
            await cabin_manager.init_db()
            print("✅ [Cabin] Đã khởi tạo cơ sở dữ liệu và nạp các phiên cabin còn hiệu lực thành công.", flush=True)
        except Exception as e:
            print(f"❌ [Cabin] Lỗi khởi tạo DB cabin: {e}", flush=True)

    def cog_unload(self):
        self.cleanup_task.cancel()
        for task in self._debounce_tasks.values():
            task.cancel()
        self._debounce_tasks.clear()
        self._msg_buffers.clear()

    @tasks.loop(seconds=60.0)
    async def cleanup_task(self):
        """Tự động dọn dẹp các phiên cabin đã hết hạn định kỳ mỗi 60 giây."""
        try:
            cleaned = await cabin_manager.cleanup_expired()
            if cleaned > 0:
                print(f"🧹 [Cabin] Đã tự động dọn dẹp {cleaned} phiên cabin đã hết hạn.", flush=True)
        except Exception as e:
            print(f"⚠️ [Cabin] Lỗi dọn dẹp session hết hạn: {e}", flush=True)

    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()

    # =========================================================================
    # LISTENER: on_message -> Debounce Buffer -> Dich Cabin Batch
    # =========================================================================

    # Thoi gian cho de gom tin nhan truoc khi goi AI (giay)
    BATCH_DEBOUNCE_SECONDS = 3.0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Bo qua tin nhan tu bot hoac ngoai guild hoac khong co noi dung
        if message.author.bot or not message.guild or not message.content:
            return

        guild_id = message.guild.id
        author_id = message.author.id
        raw_text = message.content.strip()

        # Kiem tra neu la tin nhan lenh bot (.m, .M, /, !, ?, ;, ~, $)
        is_bot_cmd = raw_text.startswith((".m", ".M", "/", "!", "?", ";", "~", "$"))

        # Ghi nhan vao RAM rolling cache neu khong phai lenh bot (<0.001ms)
        if not is_bot_cmd:
            cabin_manager.record_channel_message(
                guild_id=guild_id,
                channel_id=message.channel.id,
                author_name=message.author.display_name,
                content=message.clean_content
            )

        # 2. Kiem tra xem tac gia co dang trong phien cabin cua guild nay khong
        session = cabin_manager.get_session(guild_id, author_id)
        if not session:
            return

        # 3. Loc bo cac tin nhan khong phu hop de dich
        if is_bot_cmd or len(raw_text) < 2:
            return

        # Bo qua neu chi chua link URL thuan tuy
        if raw_text.startswith(("http://", "https://")) and " " not in raw_text:
            return

        # 4. Kiem tra Cooldown nhanh (check-only, khong update - update that su khi AI xong)
        if not cabin_manager.check_cooldown(guild_id, author_id, update=False):
            return

        # 5. Buffer tin nhan vao debounce window
        buf_key = (guild_id, author_id)
        self._msg_buffers[buf_key].append((message.clean_content.strip(), message))

        # Huy debounce task cu neu dang cho
        existing_task = self._debounce_tasks.get(buf_key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        # Tao debounce task moi - sau BATCH_DEBOUNCE_SECONDS se thuc hien dich tong hop
        task = asyncio.create_task(
            self._process_cabin_batch(buf_key, guild_id, author_id, message)
        )
        self._debounce_tasks[buf_key] = task

    async def _process_cabin_batch(
        self,
        buf_key: tuple,
        guild_id: int,
        author_id: int,
        trigger_message: discord.Message,
    ):
        """
        Cho BATCH_DEBOUNCE_SECONDS roi xu ly toan bo tin nhan da gom trong buffer.
        Neu nhieu tin nhan duoc gom lai, goi AI 1 lan duy nhat voi batch prompt de giam RPM.
        """
        try:
            await asyncio.sleep(self.BATCH_DEBOUNCE_SECONDS)
        except asyncio.CancelledError:
            # Task bi huy do co tin nhan moi den - task moi se xu ly
            return

        # Lay va xoa buffer
        batch_entries = self._msg_buffers.pop(buf_key, [])
        self._debounce_tasks.pop(buf_key, None)

        if not batch_entries:
            return

        # Kiem tra lai cooldown (lock that su ngay truoc khi goi AI)
        if not cabin_manager.check_cooldown(guild_id, author_id, update=True):
            return

        # Kiem tra lai session van con hieu luc
        session = cabin_manager.get_session(guild_id, author_id)
        if not session:
            cabin_manager.reset_cooldown(guild_id, author_id)
            return

        start_time = time.time()
        target_name = trigger_message.author.display_name

        # Gom danh sach text va lay tin nhan gan nhat de reply vao
        texts = [text for text, _ in batch_entries]
        reply_target = batch_entries[-1][1]  # Reply vao tin nhan cuoi cung trong batch
        count = len(texts)
        log_label = f"batch {count} tin" if count > 1 else "1 tin"

        # Lay boi canh kenh
        context_tuples = await cabin_manager.get_channel_context(
            channel=trigger_message.channel,
            window_minutes=CONTEXT_HISTORY_MINUTES,
            max_messages=CONTEXT_MAX_MESSAGES
        )
        # Loc bo cac tin nhan trong batch khoi context (tranh lap lai)
        batch_texts_set = set(texts)
        context_tuples = [c for c in context_tuples if c[1].strip() not in batch_texts_set]

        try:
            async with trigger_message.channel.typing():
                interpretation = await generate_cabin_interpretation_batch(
                    target_name=target_name,
                    messages=texts,
                    context_messages=context_tuples,
                )

                if interpretation:
                    reply_content = f"\U0001f3ae **Dich cabin:** {interpretation}"
                    await reply_target.reply(reply_content, mention_author=False)

                    cabin_manager.update_cooldown(guild_id, author_id)
                    await cabin_manager.increment_translated_count(guild_id, author_id)

                    duration_ms = round((time.time() - start_time) * 1000, 2)
                    activity_logger.log(
                        action_type="cabin",
                        action_name="Dich Cabin AI",
                        user_id=author_id,
                        user_name=target_name,
                        user_avatar=str(trigger_message.author.display_avatar.url) if trigger_message.author.display_avatar else None,
                        guild_name=trigger_message.guild.name,
                        guild_id=guild_id,
                        channel_name=trigger_message.channel.name if hasattr(trigger_message.channel, "name") else "unknown",
                        channel_id=trigger_message.channel.id,
                        prompt=" | ".join(texts)[:150],
                        response=interpretation[:200],
                        status="success",
                        duration_ms=duration_ms,
                    )
                    print(f"[Cabin] Dich {log_label} cua [{target_name}] xong trong {duration_ms:.0f}ms.", flush=True)
                else:
                    # AI khong sinh duoc ket qua, reset cooldown de tin tiep theo khong bi chan
                    cabin_manager.reset_cooldown(guild_id, author_id)
        except discord.Forbidden:
            cabin_manager.reset_cooldown(guild_id, author_id)
            print(f"[Cabin] Bot thieu quyen gui tin nhan tai channel {trigger_message.channel.id}", flush=True)
        except Exception as err:
            cabin_manager.reset_cooldown(guild_id, author_id)
            print(f"[Cabin] Loi trong qua trinh dich {log_label}: {err}", flush=True)
            import traceback as _tb
            _tb.print_exc()



async def setup(bot: commands.Bot):
    await bot.add_cog(CabinCog(bot))
