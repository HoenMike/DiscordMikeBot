import discord
from discord.ext import commands
import sys
import traceback
from core.config_manager import ConfigManager

intents = discord.Intents.default()
intents.message_content = True

FEATURE_EXTENSIONS = [
    "features.embed.cog",
    "features.summary.cog",
    "features.tarot.cog",
]


def get_prefix(bot, message):
    """Hỗ trợ các prefix $m, $M và Bot Mention linh hoạt."""
    prefixes = ["$m ", "$m", "$M ", "$M"]
    if bot.user:
        return commands.when_mentioned_or(*prefixes)(bot, message)
    return prefixes


class SummaryBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            case_insensitive=True,
            help_command=None  # Sử dụng custom help command bên dưới
        )
        self.config_manager = ConfigManager()

    async def setup_hook(self):
        await self.config_manager.init_db()

        for ext in FEATURE_EXTENSIONS:
            try:
                await self.load_extension(ext)
                print(f"✅ Đã tải thành công extension: {ext}", flush=True)
            except Exception as cog_error:
                print(f"⚠️ Bỏ qua extension '{ext}' do không khả dụng hoặc lỗi: {cog_error}", flush=True)
                traceback.print_exc(file=sys.stdout)

        print("🔄 Đang đồng bộ hóa Slash Commands...", flush=True)
        try:
            synced = await self.tree.sync()
            print(f"🎉 Đã đồng bộ hóa {len(synced)} Slash Commands toàn cầu thành công!", flush=True)
        except Exception as sync_error:
            print(f"❌ Lỗi khi đồng bộ hóa Slash Commands: {sync_error}", flush=True)
            traceback.print_exc(file=sys.stdout)

        # Xử lý lỗi toàn cục cho Slash Commands (bao gồm Cooldown)
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
            if isinstance(error, discord.app_commands.CommandOnCooldown):
                msg = f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng đợi `{int(error.retry_after) + 1}s` nữa trước khi dùng lại lệnh."
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
            else:
                print(f"❌ [Slash Command Error] {error}", flush=True)
                traceback.print_exception(type(error), error, error.__traceback__, file=sys.stdout)

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Xử lý lỗi toàn cục cho các lệnh Prefix ($m ...)."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"⏳ **Bạn đang thao tác quá nhanh!** Vui lòng đợi `{int(error.retry_after) + 1}s` nữa trước khi dùng lại lệnh.",
                mention_author=False
            )
            return
        elif isinstance(error, commands.CommandNotFound):
            return
        else:
            print(f"⚠️ [Prefix Command Error] {error}", flush=True)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Nếu người dùng chỉ gõ đúng "$m" hoặc "$M" không kèm lệnh, hiển thị bảng hướng dẫn
        content_clean = message.content.strip().lower()
        if content_clean in ["$m", "$m help"]:
            ctx = await self.get_context(message)
            if not ctx.valid or ctx.command is None:
                await send_bot_help(ctx)
                return

        await self.process_commands(message)


bot = SummaryBot()


async def send_bot_help(ctx: commands.Context):
    """Gửi bảng hướng dẫn tổng quan các lệnh của bot."""
    embed = discord.Embed(
        title="🤖 HƯỚNG DẪN SỬ DỤNG MIKEBOT",
        description=(
            "Bạn có thể sử dụng các tính năng qua **Slash Command** (`/`) "
            "hoặc **Prefix Command** (`$m`).\n"
        ),
        color=0x7851A9
    )
    embed.add_field(
        name="🔮 BỐC BÀI TAROT",
        value=(
            "• `$m tarot` : Mở giao diện tương tác chọn kiểu trải bài & người giải bài\n"
            "• `$m tarot daily` : Bốc nhanh lá bài năng lượng ngày hôm nay\n"
            "• `$m tarot yes_no <câu hỏi>` : Hỏi quẻ Có / Không (1 lá)\n"
            "• `$m tarot single <câu hỏi>` : Lời khuyên & góc nhìn trọng tâm (1 lá)\n"
            "• `$m tarot ppf <câu hỏi>` : Quá khứ - Hiện tại - Tương lai (3 lá)\n"
            "• `$m tarot choices <câu hỏi>` : So sánh 2 ngả đường A & B (3 lá)\n"
            "• `$m tarot mbs <câu hỏi>` : Tâm trí - Thể chất - Trực giác (3 lá)\n"
            "• `$m tarot horseshoe <câu hỏi>` : Trải bài Móng ngựa toàn cảnh (5 lá)\n"
            "• `$m tarot two_paths <câu hỏi>` : Phân tích rủi ro/lợi ích 2 hướng đi (5 lá)\n"
            "• `$m tarot celtic <câu hỏi>` : Trải bài Celtic Cross chuyên sâu (10 lá)\n"
            "• `$m tarot history` : Xem 5 lượt bốc bài gần nhất của bạn"
        ),
        inline=False
    )
    embed.add_field(
        name="📝 TÓM TẮT CUỘC TRÒ CHUYỆN (AI)",
        value=(
            "• `$m tomtat` : Tóm tắt nội dung kênh chat bằng AI\n"
            "• `$m tomtat [hours] [limit] [type] [focus]` : Tùy chỉnh phạm vi quét\n"
            "  *(Ví dụ: `$m tomtat 2.0 150 short`)*"
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {ctx.author.display_name} • MikeBot Hybrid Engine",
        icon_url=ctx.author.display_avatar.url if ctx.author.display_avatar else None
    )
    await ctx.reply(embed=embed, mention_author=False)


@bot.command(name="help", aliases=["huongdan", "h"])
async def help_cmd(ctx: commands.Context):
    await send_bot_help(ctx)

