import sys
import time
import traceback
from typing import Optional, Union, List, Dict
import discord
from discord import app_commands
from discord.ext import commands
from core.config_manager import ConfigManager
from core.activity_logger import activity_logger

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
        await activity_logger.init_db()

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

    async def on_ready(self):
        print(f"🎉 Bot Discord đã kết nối thành công: {self.user} (ID: {self.user.id})", flush=True)
        try:
            from core.presence_manager import presence_manager
            await presence_manager.init_db(self)
        except Exception as e:
            print(f"⚠️ [Presence] Lỗi khởi tạo presence on_ready: {e}", flush=True)

        # Kiểm tra trạng thái tạm ngừng của máy chủ trước khi xử lý Slash Command
        async def check_guild_not_suspended(interaction: discord.Interaction) -> bool:
            if interaction.guild and self.config_manager.is_guild_suspended(interaction.guild.id):
                reason = self.config_manager.get_guild_suspension_reason(interaction.guild.id) or "Quản trị viên tạm ngừng"
                guild_name = interaction.guild.name
                msg = (
                    f"⛔ **Máy chủ `{guild_name}` hiện đang bị tạm ngừng sử dụng MikeDaBot.**\n"
                    f"📝 **Lý do:** *{reason}*\n"
                    f"👉 *Vui lòng liên hệ Quản trị viên bot để biết thêm chi tiết.*"
                )
                if interaction.response.is_done():
                    await interaction.followup.send(msg, ephemeral=True)
                else:
                    await interaction.response.send_message(msg, ephemeral=True)
                return False
            return True

        self.tree.interaction_check = check_guild_not_suspended

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

        # Nếu Server đang bị Admin tạm ngừng, phản hồi lý do nếu người dùng gõ lệnh $m
        if message.guild and self.config_manager.is_guild_suspended(message.guild.id):
            if message.content.strip().startswith(("$m", "$M")):
                reason = self.config_manager.get_guild_suspension_reason(message.guild.id) or "Quản trị viên tạm ngừng"
                guild_name = message.guild.name
                msg = (
                    f"⛔ **Máy chủ `{guild_name}` hiện đang bị tạm ngừng sử dụng MikeDaBot.**\n"
                    f"📝 **Lý do:** *{reason}*\n"
                    f"👉 *Vui lòng liên hệ Quản trị viên bot để biết thêm chi tiết.*"
                )
                await message.reply(msg, mention_author=False)
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
        title="🤖 HƯỚNG DẪN SỬ DỤNG MIKEBOT (TỔNG QUAN & TÍNH NĂNG MỚI)",
        description=(
            "Chào mừng bạn đến với **MikeDaBot**! Trợ lý Discord thông minh tích hợp AI đa nhiệm, "
            "hỗ trợ cả **Slash Command** (`/`) lẫn **Prefix Command** (`$m`, `$M`).\n\n"
            "💡 *Hãy sử dụng menu thả xuống bên dưới để tra cứu chi tiết từng tính năng & cơ chế QoL!*"
        ),
        color=0x7851A9
    )
    embed.add_field(
        name="🔮 1. BỐC BÀI TAROT (CHIÊM TINH)",
        value=(
            "• Rút bài 78 lá Rider-Waite với hình ảnh Canvas trực quan độ phân giải cao.\n"
            "• Luận giải đa tầng với 3 tính cách Reader độc đáo (`Orion`, `Celeste`, `Jester`).\n"
            "• Hạt nhân năng lượng vũ trụ theo khung giờ (1 tiếng/khung) & Nút đánh giá phản hồi.\n"
            "👉 **Lệnh:** `/tarot`, `$m tarot` | **Xem chi tiết:** Chọn mục `🔮 Tarot` bên dưới."
        ),
        inline=False
    )
    embed.add_field(
        name="📝 2. TÓM TẮT CUỘC TRÒ CHUYỆN (AI SUMMARY)",
        value=(
            "• Đọc và đúc kết nội dung kênh chat bằng Gemini Flash AI tốc độ cao.\n"
            "• Quét sâu tới 2500 tin nhắn, tự động trích xuất chủ đề, việc cần làm (Action Items) & Top thành viên.\n"
            "👉 **Lệnh:** `/tomtat`, `$m tomtat` | **Xem chi tiết:** Chọn mục `📝 Tóm tắt` bên dưới."
        ),
        inline=False
    )
    embed.add_field(
        name="👑 3. TỰ ĐỘNG FIX EMBED MẠNG XÃ HỘI (SIÊU GỌN GÀNG)",
        value=(
            "• Tự động hiển thị video/ảnh mượt mà cho **9 nền tảng**: Facebook, TikTok, Instagram, Twitter/X, Reddit, Threads, Pixiv, Bluesky, Twitch.\n"
            "• **Cơ chế QoL mới**: Bảo toàn tin nhắn & ảnh gốc 100%, Subtext trả lời siêu gọn, tự động xóa khi tin gốc bị xóa, tự động nhận diện NSFW / Spoiler.\n"
            "👉 **Lệnh quản trị:** `/autoembed`, `/nsfwmode`, `/embedconfig`, `/embedplatform`"
        ),
        inline=False
    )
    embed.add_field(
        name="⚙️ 4. HỆ THỐNG & QUẢN TRỊ (SYSTEM & STATUS)",
        value=(
            "• `/version` (`$m ver`): Xem phiên bản hiện tại & toàn bộ nhật ký cập nhật (Patchnotes).\n"
            "• `/setstatus`: Đổi trạng thái bot động (Online, Idle, DND, Xoay tua tính năng) dành cho Admin.\n"
            "• Web Dashboard Quản trị: Xem Live Console, Live Activity & cấu hình máy chủ."
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Hybrid Engine v2.4.5",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_tarot_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="🔮 HƯỚNG DẪN CHI TIẾT TÍNH NĂNG BỐC BÀI TAROT",
        description=(
            "Hệ thống Tarot kết hợp công nghệ kết xuất hình ảnh trải bài sống động, "
            "cơ chế hạt nhân năng lượng và tương tác hỏi thêm sâu sắc."
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
            "• **⚖️ Orion**: Trưởng thành, ôn hòa, điềm đạm, phân tích logic và thực tế.\n"
            "• **🌸 Celeste**: Dịu dàng, ấm áp, thấu cảm và vỗ về cảm xúc tâm hồn.\n"
            "• **🃏 Jester**: Tinh quái, trào phúng, hài hước châm biếm và 'bẻ lái' bất ngờ.\n"
            "• **🎲 Ngẫu Nhiên**: Tự động chọn ngẫu nhiên 1 trong 3 Reader."
        ),
        inline=False
    )
    embed.add_field(
        name="💡 DANH SÁCH LỆNH TAROT ĐẦY ĐỦ",
        value=(
            "• `/tarot` hoặc `$m tarot` : Mở bảng chọn kiểu bài & Reader trực quan\n"
            "• `/tarot spread:Yes / No question:Có nên đổi việc?` hoặc `$m tarot yes_no Có nên đổi việc?`\n"
            "• `/tarot_history` hoặc `$m tarot history` : Xem lại các lượt bốc bài gần nhất của bạn\n"
            "• `/tarot_recommend [question]` hoặc `$m tarot recommend [câu hỏi]` : AI gợi ý kiểu trải bài phù hợp nhất\n"
            "• `/tarot_memory [on/off]` hoặc `$m tarot memory [on/off]` : Bật / tắt trí nhớ ngữ cảnh bạn cũ\n"
            "• `/tarot_forget` hoặc `$m tarot forget` : Xóa sạch toàn bộ lịch sử bốc bài khỏi hệ thống\n"
            "• `/tarot_weekly_setup [channel]` : Cài đặt kênh nhận bài tuần vào sáng Thứ Hai (Admin)"
        ),
        inline=False
    )
    embed.add_field(
        name="🌌 CÁC TÍNH NĂNG & CƠ CHẾ QOL NỔI BẬT",
        value=(
            "• **Hạt Nhân Năng Lượng (Cosmic Seed)**: Khi hỏi cùng một câu hỏi trong vòng **1 tiếng**, "
            "vũ trụ sẽ giữ nguyên các lá bài rút ra để đảm bảo tính nhất quán (tránh vừa Có vừa Không).\n"
            "• **Nút Hỏi Thêm Ý Nghĩa (❓)**: Mở modal cho phép đặt thêm câu hỏi đào sâu hoặc xin thêm lời khuyên chi tiết cho quẻ bài vừa bốc.\n"
            "• **Nút Đánh Giá (👍 Hữu ích / 👎 Chưa chuẩn)**: Góp ý phản hồi chất lượng luận giải của AI.\n"
            "• **Trí Nhớ Bạn Cũ (Memory)**: AI có khả năng liên kết nhẹ nhàng ngữ cảnh từ các quẻ bài trước.\n"
            "• **Cooldown An Toàn**: **30 giây** giữa 2 lần bốc bài liên tiếp để giữ không gian tĩnh tâm."
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Tarot Engine v2.0",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_summary_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="📝 HƯỚNG DẪN TÍNH NĂNG TÓM TẮT CUỘC TRÒ CHUYỆN (AI)",
        description=(
            "Sử dụng Google Gemini AI để đọc và đúc kết nội dung tin nhắn trong kênh chat thành "
            "bản tóm tắt súc tích, phân loại chủ đề rõ ràng, thống kê người nói nhiều nhất và trích xuất danh sách hành động (Action Items)."
        ),
        color=0x3498DB
    )
    embed.add_field(
        name="⚙️ CÚ PHÁP SỬ DỤNG",
        value=(
            "• **Slash Command**: `/tomtat [hours] [limit] [summary_type] [focus] [date] [from_time] [to_time] [message_link] [send_to_dm] [channel]`\n"
            "• **Prefix Command**: `$m tomtat [hours] [limit] [summary_type] [focus]`\n"
            "• **Lệnh tắt / bí danh**: `$m tt`, `$m summary`"
        ),
        inline=False
    )
    embed.add_field(
        name="📊 CÁC THAM SỐ TÙY CHỌN",
        value=(
            "• `hours` *(Mặc định: 2.0h)*: Khoảng thời gian quét tin nhắn ngược về trước (Ví dụ: `0.5`, `3`, `24`).\n"
            "• `limit` *(Mặc định: 150 tin, tối đa: 2500 tin)*: Giới hạn số lượng tin nhắn quét.\n"
            "• `summary_type`: `short` (Tóm tắt ngắn gọn - mặc định) hoặc `long` (Tóm tắt dài & Timeline chi tiết).\n"
            "• `focus`: Từ khóa / chủ đề cần tập trung phân tích sâu (Ví dụ: `bug`, `game`, `họp`, `deadline`, `kèo`).\n"
            "• `date` & `from_time` / `to_time`: Quét theo ngày & khung giờ cụ thể (Ví dụ: `19/05/2024` từ `00:00` đến `04:00`).\n"
            "• `message_link`: Link tin nhắn Discord hoặc Message ID làm mốc bắt đầu quét.\n"
            "• `send_to_dm`: Gửi kết quả riêng vào DM thay vì kênh chung (gõ thêm `dm` hoặc `rieng` trong lệnh prefix)."
        ),
        inline=False
    )
    embed.add_field(
        name="💡 VÍ DỤ MẪU",
        value=(
            "• `$m tomtat` : Tóm tắt nhanh 2 tiếng gần nhất (150 tin nhắn)\n"
            "• `$m tomtat 5 300 long bug` : Quét 5 tiếng (300 tin), chi tiết timeline, tập trung vào `bug`\n"
            "• `$m tomtat 100 dm` : Quét 100 tin gần nhất và gửi kết quả vào tin nhắn riêng DM\n"
            "• `/tomtat hours:24.0 limit:500 summary_type:Tóm tắt dài & Timeline chi tiết focus:deadline`"
        ),
        inline=False
    )
    embed.add_field(
        name="🎯 CÁC ĐIỂM CẢI TIẾN THÔNG MINH (QOL)",
        value=(
            "• Tự động lọc bỏ các tin nhắn spam, tin nhắn lệnh của bot khác để bản tóm tắt không bị rác.\n"
            "• Tự động đếm và vinh danh Top thành viên đóng góp nhiều nhất trong cuộc trò chuyện.\n"
            "• Nhận diện công việc / lời hẹn cần thực hiện (Action Items) kèm tên người phụ trách."
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot Summary Engine v2.0",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


def build_embed_help_embed(user: Union[discord.User, discord.Member]) -> discord.Embed:
    embed = discord.Embed(
        title="👑 HƯỚNG DẪN TỰ ĐỘNG FIX EMBED & PREVIEW MẠNG XÃ HỘI",
        description=(
            "Tự động phát hiện các liên kết mạng xã hội bị lỗi hoặc không có video trên Discord và thay thế "
            "bằng bản xem trước siêu sắc nét, mượt mà mà vẫn giữ trọn vẹn bố cục kênh chat."
        ),
        color=0x2ECC71
    )
    embed.add_field(
        name="🌐 9 NỀN TẢNG ĐƯỢC HỖ TRỢ TỰ ĐỘNG",
        value=(
            "• **Facebook**: Reels, Watch, Video, Post (`facebed.seria.moe`)\n"
            "• **Instagram**: Reels, Video, Ảnh đơn, Carousel nhiều ảnh (`ddinstagram.com`, `vxinstagram.com`)\n"
            "• **TikTok**: Video trực tiếp, Photo Slide (`vxtiktok.com`, `tnktok.com`)\n"
            "• **Twitter / X**: Video, Ảnh HD, Bài viết dài (`fxtwitter.com`, `fixupx.com`)\n"
            "• **Reddit**: Video có âm thanh, GIF, Bài viết (`rxddit.com`, `fxreddit.seria.moe`)\n"
            "• **Threads**: Video, Ảnh bài viết, Share link (`vxthreads.com`, `fixthreads.seria.moe`)\n"
            "• **Pixiv**: Tranh minh họa, Manga nhiều trang (`phixiv.net`)\n"
            "• **Bluesky & Twitch**: Bài viết Bluesky & Clip ngắn Twitch"
        ),
        inline=False
    )
    embed.add_field(
        name="✨ CÁC CƠ CHẾ QOL & TRẢI NGHIỆM ĐỘC QUYỀN",
        value=(
            "• 🛡️ **Bảo toàn tin nhắn & ảnh gốc (Suppress Mode)**: Bot không xóa tin nhắn của bạn, giữ nguyên 100% ảnh/tệp đính kèm. Khi người khác reply tin nhắn của bạn, Discord vẫn **tự động tô vàng dòng chat (Yellow Highlight)** và gửi thông báo native.\n"
            "• 🏷️ **Subtext Jump Link siêu gọn**: Hiển thị dòng chú thích nhỏ `↩️ Trả lời [Tên](link)` ngay trên Embed, nhấp vào là cuộn ngay về tin gốc, không bị lặp chữ hay double ping.\n"
            "• 🗑️ **Tự động xóa Embed đồng bộ**: Khi bạn xóa tin nhắn gốc chứa link, Bot sẽ **tự động dọn sạch Embed tương ứng** (không để lại rác trong chat).\n"
            "• 🔞 **Force Spoiler & Nhận diện NSFW**: Tự động che mờ khi bọc trong `||link||` hoặc khi tin nhắn có từ khóa (`nsfw`, `18+`, `r18`, `spoiler`, `nhạy cảm`...)."
        ),
        inline=False
    )
    embed.add_field(
        name="🛠️ LỆNH CẤU HÌNH CHO QUẢN TRỊ VIÊN",
        value=(
            "• `/autoembed [enabled] [channel]` : Bật / tắt tính năng auto fix link cho server hoặc từng kênh riêng\n"
            "• `/nsfwmode [mode] [channel]` : Cấu hình xử lý link 18+ (`spoiler` - che mờ, `block` - chặn, `allow` - hiện thẳng)\n"
            "• `/embedplatform [platform] [enabled]` : Bật / tắt hỗ trợ cho từng nền tảng mạng xã hội\n"
            "• `/embedproxy [platform] [domain]` : Tùy chỉnh danh sách Proxy domain ưu tiên\n"
            "• `/embedconfig` : Xem bảng tổng hợp cấu hình Embed hiện tại của máy chủ"
        ),
        inline=False
    )
    embed.set_footer(
        text=f"Yêu cầu bởi {user.display_name} • MikeBot AutoEmbed v2.0",
        icon_url=user.display_avatar.url if user.display_avatar else None
    )
    return embed


class HelpView(discord.ui.View):
    """View điều hướng tương tác giữa các trang hướng dẫn của MikeBot."""

    def __init__(self, author_id: int, current_tab: str = "overview", timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.current_tab = current_tab
        self.message: Optional[discord.Message] = None
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

        # Nút Đóng / Xóa tin nhắn hướng dẫn
        btn_close = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.danger,
            custom_id="help_btn_close",
            row=1
        )
        btn_close.callback = self._handle_close
        self.add_item(btn_close)

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
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người gọi lệnh mới có thể tương tác!", ephemeral=True)
            return

        self.current_tab = interaction.data["values"][0]
        self._build_components()
        embed = self.get_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _handle_close(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người gọi lệnh mới có thể đóng hướng dẫn!", ephemeral=True)
            return

        self.clear_items()
        try:
            if self.message:
                await self.message.delete()
            else:
                await interaction.delete_original_response()
        except Exception:
            pass
        self.stop()

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            try:
                await self.message.delete()
            except Exception:
                pass


async def send_bot_help(
    target: Union[commands.Context, discord.Interaction],
    feature: str = "overview",
    ephemeral: bool = True
):
    """Hàm dùng chung gửi giao diện hướng dẫn cho cả Slash và Prefix."""
    user = target.author if isinstance(target, commands.Context) else target.user
    view = HelpView(author_id=user.id, current_tab=feature)
    embed = view.get_embed(user)

    t_help_start = time.monotonic()
    if isinstance(target, commands.Context):
        sent_msg = await target.reply(embed=embed, view=view, mention_author=False)
        view.message = sent_msg
    else:
        if target.response.is_done():
            await target.followup.send(embed=embed, view=view, ephemeral=ephemeral)
        else:
            await target.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
    elapsed_ms = round((time.monotonic() - t_help_start) * 1000, 1)

    # Ghi nhận hoạt động vào Live Activity Logger
    try:
        from core.activity_logger import activity_logger
        guild = target.guild
        channel = target.channel
        user_avatar = user.display_avatar.url if user.display_avatar else None
        activity_logger.log(
            action_type="command",
            action_name="Xem hướng dẫn (Help)",
            user_id=user.id,
            user_name=user.display_name,
            user_avatar=user_avatar,
            guild_name=guild.name if guild else "Direct Message",
            guild_id=guild.id if guild else None,
            channel_name=getattr(channel, 'name', 'Direct Message'),
            channel_id=channel.id if channel else None,
            prompt=f"Mục: {feature}",
            response="Đã hiển thị bảng hướng dẫn sử dụng tương tác.",
            status="success",
            duration_ms=elapsed_ms,
            details={"tab": feature}
        )
    except Exception as act_err:
        print(f"⚠️ [ActivityLogger] Lỗi ghi nhận Help: {act_err}", flush=True)


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
    await send_bot_help(interaction, feature=chosen, ephemeral=True)


@bot.tree.command(name="mhelp", description="Mở nhanh bảng hướng dẫn sử dụng MikeBot (Tarot, Tóm tắt, Embed)")
@app_commands.describe(feature="Chọn tính năng bạn muốn xem hướng dẫn chi tiết")
@app_commands.choices(feature=[
    app_commands.Choice(name="🔮 Bốc Bài Tarot (Chi Tiết)", value="tarot"),
    app_commands.Choice(name="📝 Tóm Tắt Tin Nhắn (AI)", value="summary"),
    app_commands.Choice(name="👑 Tự Động Fix Embed Link", value="embed"),
    app_commands.Choice(name="🌐 Tổng Quan Tất Cả Tính Năng", value="overview"),
])
async def mhelp_slash(
    interaction: discord.Interaction,
    feature: Optional[app_commands.Choice[str]] = None
):
    chosen = feature.value if feature else "overview"
    await send_bot_help(interaction, feature=chosen, ephemeral=True)


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


# ==========================================
# 6. VERSION & PATCHNOTES COMMANDS
# ==========================================
@bot.tree.command(name="version", description="Xem thông tin phiên bản và nhật ký cập nhật (Patchnotes / Changelog)")
async def version_slash(interaction: discord.Interaction):
    from core.version import build_version_embed
    embed = build_version_embed(interaction.user)
    await interaction.response.send_message(embed=embed)


@bot.command(name="version", aliases=["ver", "patchnotes", "changelog", "patchnote"])
async def version_cmd(ctx: commands.Context):
    from core.version import build_version_embed
    embed = build_version_embed(ctx.author)
    await ctx.reply(embed=embed, mention_author=False)


# ==========================================
# 7. DYNAMIC PRESENCE COMMANDS (ADMIN ONLY)
# ==========================================
@bot.tree.command(name="setstatus", description="Cập nhật trạng thái hiển thị của Bot (Quản trị viên)")
@app_commands.describe(
    status="Chọn trạng thái: online, idle, dnd, invisible",
    activity_type="Loại hoạt động: custom, playing, watching, listening, competing",
    text="Nội dung hiển thị trạng thái",
    rotating="Tự động xoay tua trạng thái tính năng định kỳ"
)
@app_commands.choices(
    status=[
        app_commands.Choice(name="Online (Trực tuyến)", value="online"),
        app_commands.Choice(name="Idle (Chờ / Đang redeploy)", value="idle"),
        app_commands.Choice(name="Do Not Disturb (Bận / Đang fix bug)", value="dnd"),
        app_commands.Choice(name="Invisible (Ẩn)", value="invisible"),
    ],
    activity_type=[
        app_commands.Choice(name="Custom Status (Tùy chỉnh)", value="custom"),
        app_commands.Choice(name="Playing (Đang chơi)", value="playing"),
        app_commands.Choice(name="Watching (Đang xem)", value="watching"),
        app_commands.Choice(name="Listening (Đang nghe)", value="listening"),
        app_commands.Choice(name="Competing (Đang thi đấu)", value="competing"),
    ]
)
@app_commands.checks.has_permissions(administrator=True)
async def setstatus_slash(
    interaction: discord.Interaction,
    status: app_commands.Choice[str],
    activity_type: Optional[app_commands.Choice[str]] = None,
    text: Optional[str] = None,
    rotating: Optional[bool] = None
):
    from core.presence_manager import presence_manager
    act_type = activity_type.value if activity_type else "custom"
    is_rot = rotating if rotating is not None else False
    status_val = status.value
    status_text = text or f"Live | $m help"

    success = await presence_manager.apply_presence(
        bot=bot,
        status=status_val,
        activity_type=act_type,
        text=status_text,
        is_rotating=is_rot,
        save_db=True
    )
    if success:
        mode_str = " (Xoay tua tự động)" if is_rot else ""
        await interaction.response.send_message(
            f"✨ **Đã cập nhật trạng thái bot thành công!**\n"
            f"• Trạng thái: **{status_val.upper()}**\n"
            f"• Loại hoạt động: **{act_type}**\n"
            f"• Nội dung: `{status_text}`{mode_str}",
            ephemeral=True
        )
    else:
        await interaction.response.send_message("❌ Không thể cập nhật trạng thái bot lúc này.", ephemeral=True)


@bot.command(name="setstatus", aliases=["status", "setpresence"])
@commands.has_permissions(administrator=True)
async def setstatus_cmd(ctx: commands.Context, status_arg: str = "online", *, text_arg: str = ""):
    from core.presence_manager import presence_manager
    status_val = status_arg.lower()
    if status_val not in ["online", "idle", "dnd", "invisible"]:
        status_val = "online"
        text_arg = f"{status_arg} {text_arg}".strip()

    status_text = text_arg or "Live | $m help"
    success = await presence_manager.apply_presence(
        bot=bot,
        status=status_val,
        activity_type="custom",
        text=status_text,
        is_rotating=False,
        save_db=True
    )
    if success:
        await ctx.reply(f"✨ Đã cập nhật trạng thái bot: `[{status_val.upper()}]` {status_text}", mention_author=False)
    else:
        await ctx.reply("❌ Cập nhật trạng thái thất bại.", mention_author=False)

