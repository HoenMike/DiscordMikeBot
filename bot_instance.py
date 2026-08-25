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


# =========================================================================
# 📚 HỆ THỐNG HƯỚNG DẪN TƯƠNG TÁC (INTERACTIVE HELP SYSTEM)
# =========================================================================

def build_overview_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="🤖 HƯỚNG DẪN SỬ DỤNG MIKEBOT (TỔNG QUAN)",
        description=(
            "Chào mừng bạn đến với **MikeBot**! Bạn có thể sử dụng tất cả tính năng qua "
            "**Slash Command** (`/`) hoặc **Prefix Command** (`$m`).\n\n"
            "💡 *Hãy sử dụng menu thả xuống bên dưới để xem hướng dẫn chi tiết từng tính năng!*"
        ),
        color=0x7851A9
    )
    embed.add_field(
        name="🔮 1. BỐC BÀI TAROT (AI CHIÊM TINH)",
        value=(
            "• Rút bài 78 lá Rider-Waite với hình ảnh Canvas trực quan.\n"
            "• Luận giải bằng AI đa tầng với 3 tính cách Reader độc đáo.\n"
            "• Hạt nhân năng lượng vũ trụ theo khung giờ (1 tiếng/khung).\n"
            "👉 **Lệnh:** `/tarot`, `$m tarot` | **Xem chi tiết:** Chọn mục `🔮 Tarot` bên dưới."
        ),
        inline=False
    )
    embed.add_field(
        name="📝 2. TÓM TẮT CUỘC TRÒ CHUYỆN (AI SUMMARY)",
        value=(
            "• Tóm tắt thông minh nội dung kênh chat bằng Gemini Flash AI.\n"
            "• Tùy chỉnh số giờ quét, số lượng tin nhắn và từ khóa trọng tâm.\n"
            "👉 **Lệnh:** `/tomtat`, `$m tomtat` | **Xem chi tiết:** Chọn mục `📝 Tóm tắt` bên dưới."
        ),
        inline=False
    )
    embed.add_field(
        name="👑 3. TỰ ĐỘNG FIX EMBED LIÊN KẾT",
        value=(
            "• Tự động hiển thị video/ảnh cho TikTok, Instagram, Twitter/X, Reddit, Threads.\n"
            "👉 **Lệnh quản trị:** `/autoembed`, `/embedconfig`"
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Hybrid Engine",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_tarot_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="🔮 HƯỚNG DẪN CHI TIẾT TÍNH NĂNG BỐC BÀI TAROT",
        description=(
            "Hệ thống Tarot tích hợp trí tuệ nhân tạo (AI Deep Reasoning) kết hợp công nghệ "
            "kết xuất hình ảnh trải bài sống động và cơ chế hạt nhân năng lượng theo khung giờ."
        ),
        color=0x9B59B6
    )
    embed.add_field(
        name="🃏 9 KIỂU TRẢI BÀI CHUYÊN SÂU",
        value=(
            "• `daily` : **🌟 Daily Card (1 lá)** — Năng lượng & thông điệp ngày (Reset 00:00 VN)\n"
            "• `yes_no` : **⚡ Yes / No (1 lá)** — Phán quyết Có / Không dứt khoát kèm phân tích\n"
            "• `single` : **🎯 Single Card (1 lá)** — Lời khuyên cốt lõi & góc nhìn trọng tâm\n"
            "• `ppf` : **⏳ Past - Present - Future (3 lá)** — Quá khứ ➔ Hiện tại ➔ Tương lai\n"
            "• `choices` : **⚖️ Two Choices (3 lá)** — So sánh nhanh 2 phương án A & B\n"
            "• `mbs` : **🧘 Mind - Body - Spirit (3 lá)** — Tâm trí ➔ Thể chất ➔ Trực giác\n"
            "• `horseshoe` : **🧲 Horseshoe Spread (5 lá)** — Toàn cảnh vấn đề & chướng ngại vật\n"
            "• `two_paths` : **🌿 Two Paths (5 lá)** — Phân tích chi tiết rủi ro & cơ hội 2 hướng\n"
            "• `celtic` : **👑 Celtic Cross (10 lá)** — Trải bài chữ thập toàn diện 10 góc nhìn"
        ),
        inline=False
    )
    embed.add_field(
        name="🎭 3 NGƯỜI GIẢI BÀI (AI READERS)",
        value=(
            "• **⚖️ Orion**: Trưởng thành, ôn hòa, điềm đạm và sâu sắc.\n"
            "• **🌸 Celeste**: Dịu dàng, ấm áp, thấu cảm và vỗ về tâm hồn.\n"
            "• **🃏 Jester**: Tinh quái, trào phúng, hài hước châm biếm và 'bẻ lái' bất ngờ.\n"
            "• **🎲 Ngẫu Nhiên**: Tự động chọn 1 trong 3 Reader ngẫu nhiên."
        ),
        inline=False
    )
    embed.add_field(
        name="💡 CÚ PHÁP SỬ DỤNG",
        value=(
            "**1. Mở Bảng Chọn Trực Quan:**\n"
            "• `/tarot` hoặc `$m tarot` *(Chọn kiểu bài & nhập câu hỏi trực tiếp trên menu)*\n\n"
            "**2. Bốc Nhanh Qua Lệnh:**\n"
            "• `/tarot spread:Yes / No question:Có nên chuyển việc?`\n"
            "• `$m tarot yes_no Tôi có nên đầu tư vào dự án này không?`\n"
            "• `$m tarot daily` *(Rút bài năng lượng ngày)*\n\n"
            "**3. Xem Lịch Sử Bốc Bài:**\n"
            "• `/tarot_history` hoặc `$m tarot history`"
        ),
        inline=False
    )
    embed.add_field(
        name="🌌 QUY TẮC NĂNG LƯỢNG VŨ TRỤ & COOLDOWN",
        value=(
            "• **Hạt Nhân Năng Lượng (Cosmic Seed)**: Nếu bạn hỏi cùng 1 câu hỏi trong vòng **1 tiếng**, "
            "vũ trụ sẽ giữ nguyên các lá bài rút ra để đảm bảo tính nhất quán (tránh vừa nói Có xong lại nói Không).\n"
            "• **Cooldown**: **30 giây** giữa 2 lần bốc bài liên tiếp để giữ không gian tĩnh tâm."
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Tarot Engine",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_summary_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="📝 HƯỚNG DẪN TÍNH NĂNG TÓM TẮT CUỘC TRÒ CHUYỆN (AI)",
        description=(
            "Sử dụng Google Gemini AI để đọc và đúc kết nội dung tin nhắn trong kênh chat thành "
            "bản tóm tắt súc tích, phân loại chủ đề rõ ràng và trích xuất danh sách hành động cần làm."
        ),
        color=0x3498DB
    )
    embed.add_field(
        name="⚙️ CÚ PHÁP SỬ DỤNG",
        value=(
            "• **Slash Command**: `/tomtat [hours] [limit] [type] [focus]`\n"
            "• **Prefix Command**: `$m tomtat [hours] [limit] [type] [focus]`"
        ),
        inline=False
    )
    embed.add_field(
        name="📊 CÁC THAM SỐ TÙY CHỌN",
        value=(
            "• `hours` *(Mặc định: 2.0h)*: Khoảng thời gian quét tin nhắn ngược về trước.\n"
            "• `limit` *(Mặc định: 150 tin, tối đa: 2500 tin)*: Giới hạn số tin nhắn quét.\n"
            "• `type`: Kiểu tóm tắt (`short` - Ngắn gọn, `detailed` - Chi tiết, `bullet` - Gạch đầu dòng).\n"
            "• `focus`: Từ khóa trọng tâm cần đào sâu (Ví dụ: `bug`, `game`, `họp`, `deadline`)."
        ),
        inline=False
    )
    embed.add_field(
        name="💡 VÍ DỤ MẪU",
        value=(
            "• `$m tomtat` : Tóm tắt nhanh 2 tiếng gần nhất (150 tin nhắn)\n"
            "• `$m tomtat 5 300 detailed bug` : Quét 5 tiếng (300 tin), chi tiết, tập trung vào `bug`\n"
            "• `/tomtat hours:24.0 limit:500 type:detailed`"
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Summary Engine",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_embed_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="👑 HƯỚNG DẪN TÍNH NĂNG FIX EMBED LIÊN KẾT",
        description=(
            "Tự động phát hiện và chuyển đổi các liên kết mạng xã hội sang dịch vụ fix embed "
            "để Discord hiển thị video và ảnh thumbnail mượt mà nhất."
        ),
        color=0x2ECC71
    )
    embed.add_field(
        name="🌐 CÁC NỀN TẢNG ĐƯỢC HỖ TRỢ",
        value=(
            "• **TikTok**: Chuyển sang `tnktok.com` để xem video trực tiếp\n"
            "• **Instagram**: Chuyển Reels & Post sang `ddinstagram.com`\n"
            "• **Twitter / X**: Chuyển sang `fixupx.com` / `fxtwitter.com`\n"
            "• **Reddit**: Chuyển sang `rxddit.com`\n"
            "• **Threads**: Chuyển sang `fixthreads.net`"
        ),
        inline=False
    )
    embed.add_field(
        name="🛠️ LỆNH CẤU HÌNH (QUẢN TRỊ VIÊN)",
        value=(
            "• `/autoembed [enabled]` : Bật / tắt tính năng auto fix link trên máy chủ / kênh\n"
            "• `/nsfwmode [mode]` : Cấu hình xử lý link nhạy cảm (`allow`, `warn`, `block`)\n"
            "• `/embedplatform [platform] [enabled]` : Bật / tắt hỗ trợ cho từng nền tảng\n"
            "• `/embedconfig` : Xem bảng cấu hình embed hiện tại của máy chủ"
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot AutoEmbed",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


class HelpView(discord.ui.View):
    """View điều hướng tương tác giữa các trang hướng dẫn của MikeBot."""

    def __init__(self, author_id: int, current_tab: str = "overview", timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.current_tab = current_tab
        self._build_components()

    def _build_components(self):
        self.clear_items()
        select = discord.ui.Select(
            placeholder="📖 Chọn danh mục hướng dẫn...",
            options=[
                discord.SelectOption(
                    label="🌐 Tổng Quan Tính Năng",
                    value="overview",
                    description="Xem tổng quan tất cả các lệnh của MikeBot",
                    default=(self.current_tab == "overview")
                ),
                discord.SelectOption(
                    label="🔮 Bốc Bài Tarot (Chi Tiết)",
                    value="tarot",
                    description="Hướng dẫn 9 trải bài, 3 Reader & cú pháp bốc Tarot",
                    default=(self.current_tab == "tarot")
                ),
                discord.SelectOption(
                    label="📝 Tóm Tắt Tin Nhắn (AI)",
                    value="summary",
                    description="Hướng dẫn tóm tắt kênh chat bằng Gemini Flash",
                    default=(self.current_tab == "summary")
                ),
                discord.SelectOption(
                    label="👑 Tự Động Embed Liên Kết",
                    value="embed",
                    description="Hướng dẫn và cấu hình tự động sửa link MXH",
                    default=(self.current_tab == "embed")
                ),
            ],
            row=0
        )
        select.callback = self._handle_select
        self.add_item(select)

    def get_embed(self, user: Union[discord.User, discord.Member]) -> discord.Embed:
        if self.current_tab == "tarot":
            return build_tarot_help_embed(user)
        elif self.current_tab == "summary":
            return build_summary_help_embed(user)
        elif self.current_tab == "embed":
            return build_embed_help_embed(user)
        else:
            return build_overview_embed(user)

    async def _handle_select(self, interaction: discord.Interaction):
        self.current_tab = interaction.data["values"][0]
        self._build_components()
        embed = self.get_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)


async def send_bot_help(
    target: Union[commands.Context, discord.Interaction],
    feature: str = "overview",
    ephemeral: bool = False
):
    """Hàm dùng chung gửi giao diện hướng dẫn cho cả Slash và Prefix."""
    user = target.author if isinstance(target, commands.Context) else target.user
    view = HelpView(author_id=user.id, current_tab=feature)
    embed = view.get_embed(user)

    if isinstance(target, commands.Context):
        await target.reply(embed=embed, view=view, mention_author=False)
    else:
        if target.response.is_done():
            await target.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await target.response.send_message(embed=embed, view=view, ephemeral=ephemeral)


@bot.tree.command(name="help", description="Xem hướng dẫn sử dụng chi tiết các tính năng của MikeBot")
@app_commands.describe(feature="Chọn tính năng bạn muốn xem hướng dẫn chi tiết")
@app_commands.choices(feature=[
    app_commands.Choice(name="🔮 Bốc Bài Tarot (Chi Tiết)", value="tarot"),
    app_commands.Choice(name="📝 Tóm Tắt Tin Nhắn (AI)", value="summary"),
    app_commands.Choice(name="👑 Tự Động Fix Embed Link", value="embed"),
    app_commands.Choice(name="🌐 Tổng Quan Tất Cả Tính Năng", value="overview"),
])
async def help_slash(
    interaction: discord.Interaction,
    feature: Optional[app_commands.Choice[str]] = None
):
    chosen = feature.value if feature else "overview"
    await send_bot_help(interaction, feature=chosen, ephemeral=False)


@bot.command(name="help", aliases=["huongdan", "h"])
async def help_cmd(ctx: commands.Context, *, feature_arg: Optional[str] = None):
    chosen = "overview"
    if feature_arg:
        arg_lower = feature_arg.strip().lower()
        if arg_lower in ["tarot", "tr", "bocbai", "boi", "tarotcard"]:
            chosen = "tarot"
        elif arg_lower in ["tomtat", "summary", "sum", "chat"]:
            chosen = "summary"
        elif arg_lower in ["embed", "fixembed", "link"]:
            chosen = "embed"
    await send_bot_help(ctx, feature=chosen)

