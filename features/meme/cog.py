import discord
from discord import app_commands
from discord.ext import commands
import sys
import traceback
from typing import Optional, List, Dict, Any
import config

from features.meme.manager import MemeManager
from features.meme.ai import MemeAI
from features.meme.fetcher import MemeFetcher
from features.meme.meme_view import MemeInteractiveView


class MemeCog(commands.Cog):
    """Cog quản lý tính năng Meme Engine thông minh (Hybrid Vector Search + Auto Crawl/Ingest + Contextual Reaction)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.meme_manager = MemeManager()
        # Đăng ký các Message Context Menus (chuột phải vào tin nhắn)
        self.ctx_menu_react = app_commands.ContextMenu(
            name="Thả Meme Hợp Cảnh",
            callback=self.context_menu_react_meme,
        )
        self.ctx_menu_save = app_commands.ContextMenu(
            name="Lưu Vào Kho Meme",
            callback=self.context_menu_save_meme,
        )
        self.bot.tree.add_command(self.ctx_menu_react)
        self.bot.tree.add_command(self.ctx_menu_save)

    async def cog_load(self):
        """Khởi tạo SQLite DB và nạp Seed Vault khi tải Cog."""
        await self.meme_manager.init_db()
        await self.meme_manager.seed_vault_if_empty(MemeAI.get_embedding)

    async def cog_unload(self):
        """Dọn dẹp Context Menu khi gỡ Cog."""
        self.bot.tree.remove_command(self.ctx_menu_react.name, type=self.ctx_menu_react.type)
        self.bot.tree.remove_command(self.ctx_menu_save.name, type=self.ctx_menu_save.type)

    async def _execute_meme_search(
        self,
        prompt: str,
        user: discord.User | discord.Member,
        chat_context: Optional[str] = None,
        interaction: Optional[discord.Interaction] = None,
        ctx: Optional[commands.Context] = None
    ):
        """Hàm dùng chung xử lý luồng tìm kiếm Meme thông minh (Hybrid Vector Search + Fallback Web Discovery)."""
        prompt_clean = prompt.strip()
        if not prompt_clean:
            err_msg = "⚠️ Vui lòng nhập từ khóa, ngữ cảnh hoặc cảm xúc bạn muốn tìm meme!"
            if interaction:
                await interaction.response.send_message(err_msg, ephemeral=True)
            elif ctx:
                await ctx.reply(err_msg, mention_author=False)
            return

        # 1. Báo trạng thái đang tìm kiếm
        if interaction:
            if not interaction.response.is_done():
                await interaction.response.defer()
        elif ctx:
            await ctx.channel.typing()

        try:
            # 2. Bước 1: Vector Search trong kho nội bộ
            # 2. Bước 1: Tra cứu Vector Search & Keyword Search trong kho nội bộ
            local_matches = []
            keyword_matches = await self.meme_manager.search_keywords(prompt_clean, limit=3)
            query_vector = await MemeAI.get_embedding(prompt_clean)
            if query_vector:
                vector_matches = await self.meme_manager.search_vector(query_vector, top_k=3, threshold=0.75)
                # Gộp kết quả keyword và vector (ưu tiên keyword nếu khớp chính xác tên meme)
                seen_ids = set()
                for m in keyword_matches + vector_matches:
                    if m["id"] not in seen_ids:
                        seen_ids.add(m["id"])
                        local_matches.append(m)

            candidates = []
            ai_data = {}

            # Nếu có kết quả Vector/Keyword HIT
            if local_matches and (keyword_matches or local_matches[0]["similarity"] >= 0.75):
                candidates = local_matches
                best_hit = local_matches[0]
                await self.meme_manager.use_meme(best_hit["id"])
                ai_data = {
                    "vibe": best_hit.get("vibe", "Hài hước"),
                    "matched_meme": best_hit.get("title", "Meme"),
                    "caption": best_hit.get("caption", f"Tâm trạng: {prompt_clean}")
                }
            else:
                # Bước 2: Phân tích sâu ngữ cảnh bằng Gemini Reasoning & Web Discovery
                ai_data = await MemeAI.reason_meme_context(prompt_clean, chat_context)
                web_results = await MemeFetcher.discover_meme(
                    vi_keywords=ai_data.get("vi_keywords", prompt_clean),
                    en_keywords=ai_data.get("en_keywords", prompt_clean),
                    raw_prompt=prompt_clean
                )

                # Ghép kết quả nội bộ (nếu có) và kết quả Web
                candidates = local_matches + web_results

            if not candidates:
                # Fallback lấy meme ngẫu nhiên nếu không tìm thấy gì
                fallback = await self.meme_manager.get_random_meme()
                if fallback:
                    candidates = [fallback]

            if not candidates:
                no_res = f"❌ Không tìm thấy meme nào phù hợp với ngữ cảnh: **{prompt_clean}**."
                if interaction:
                    await interaction.followup.send(no_res)
                elif ctx:
                    await ctx.reply(no_res, mention_author=False)
                return

            # Gửi giao diện tương tác Meme
            view = MemeInteractiveView(
                author_id=user.id,
                meme_manager=self.meme_manager,
                candidates=candidates,
                current_index=0,
                prompt=prompt_clean,
                ai_data=ai_data
            )
            embed = view.build_embed(user)

            if interaction:
                sent_msg = await interaction.followup.send(embed=embed, view=view)
                view.message = sent_msg
            elif ctx:
                # Tự động xóa tin nhắn lệnh $m meme của người dùng nếu ở server
                if ctx.guild:
                    try:
                        await ctx.message.delete()
                    except Exception:
                        pass
                sent_msg = await ctx.send(embed=embed, view=view)
                view.message = sent_msg

            config.meme_count += 1

        except Exception as e:
            print(f"[MemeCog] Lỗi xử lý meme search: {e}", flush=True)
            traceback.print_exc(file=sys.stdout)
            err_text = "❌ Đã xảy ra lỗi trong quá trình tìm kiếm meme!"
            if interaction:
                await interaction.followup.send(err_text, ephemeral=True)
            elif ctx:
                await ctx.reply(err_text, mention_author=False)

    # =========================================================================
    # 1. SLASH COMMANDS (/meme, /meme_random, /meme_stats, /meme_add)
    # =========================================================================
    @app_commands.command(
        name="meme",
        description="Gửi meme chuẩn vibe theo ngữ cảnh, cảm xúc hoặc câu chuyện bạn nhập"
    )
    @app_commands.describe(prompt="Cảm xúc, tình huống hoặc meme bạn muốn tìm (Ví dụ: bất lực nhưng phải cười, độ mixi cay...)")
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def meme_slash(self, interaction: discord.Interaction, prompt: str):
        await self._execute_meme_search(prompt=prompt, user=interaction.user, interaction=interaction)

    @app_commands.command(
        name="meme_random",
        description="Bốc ngẫu nhiên một meme hài hước từ Kho Meme Vector"
    )
    @app_commands.checks.cooldown(1, 10.0, key=lambda i: i.user.id)
    async def meme_random_slash(self, interaction: discord.Interaction):
        await interaction.response.defer()
        meme = await self.meme_manager.get_random_meme()
        if not meme:
            await interaction.followup.send("⚠️ Kho meme hiện đang trống!")
            return

        await self.meme_manager.use_meme(meme["id"])
        view = MemeInteractiveView(
            author_id=interaction.user.id,
            meme_manager=self.meme_manager,
            candidates=[meme],
            current_index=0,
            prompt="Meme ngẫu nhiên"
        )
        embed = view.build_embed(interaction.user)
        sent_msg = await interaction.followup.send(embed=embed, view=view)
        view.message = sent_msg

    @app_commands.command(
        name="meme_stats",
        description="Xem thống kê tổng quan và bảng xếp hạng Top Meme được yêu thích nhất"
    )
    async def meme_stats_slash(self, interaction: discord.Interaction):
        stats = await self.meme_manager.get_stats()
        embed = discord.Embed(
            title="📊 THỐNG KÊ KHO MEME VECTOR (MEME VAULT)",
            description=(
                f"• 📦 **Tổng số meme trong kho:** `{stats['total_memes']}`\n"
                f"• ❤️ **Tổng lượt thả tim:** `{stats['total_likes']}`\n"
                f"• 🚀 **Tổng lượt sử dụng:** `{stats['total_uses']}`"
            ),
            color=0xF1C40F
        )

        top_list = stats.get("top_memes", [])
        if top_list:
            lines = [
                f"`#{i+1}` **{m['title']}** — ❤️ {m['likes']} thích • 🚀 {m['uses']} lượt dùng"
                for i, m in enumerate(top_list)
            ]
            embed.add_field(name="🏆 Top 5 Meme Được Sử Dụng Nhiều Nhất", value="\n".join(lines), inline=False)

        embed.set_footer(
            text=f"Yêu cầu bởi {interaction.user.display_name} • MikeBot Meme Engine",
            icon_url=interaction.user.display_avatar.url if interaction.user.display_avatar else None
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="meme_add",
        description="Thêm một ảnh/GIF meme mới vào kho dữ liệu kèm AI tự động gắn thẻ"
    )
    @app_commands.describe(
        url="Đường dẫn liên kết trực tiếp tới ảnh hoặc GIF meme",
        title="Tên hoặc mô tả ngắn của meme (để trống AI sẽ tự nhận diện)"
    )
    async def meme_add_slash(
        self,
        interaction: discord.Interaction,
        url: str,
        title: Optional[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        # Sử dụng Vision AI để quét nội dung ảnh
        analysis = await MemeAI.analyze_image_with_vision(url)
        final_title = title.strip() if title else analysis.get("title", "Meme mới")
        vibe = analysis.get("vibe", "Hài hước")
        caption = analysis.get("caption", "Meme được đóng góp")
        tags = analysis.get("tags", ["meme", "user_upload"])

        text_to_embed = f"Title: {final_title}. Vibe: {vibe}. Tags: {', '.join(tags)}. Caption: {caption}"
        vector = await MemeAI.get_embedding(text_to_embed)

        saved_id = await self.meme_manager.add_meme(
            title=final_title,
            url=url,
            media_type="gif" if ".gif" in url.lower() else "image",
            caption=caption,
            tags=tags,
            vibe=vibe,
            vector=vector,
            source="user_upload",
            added_by=interaction.user.display_name
        )

        if saved_id:
            await interaction.followup.send(
                f"✅ **Đã thêm thành công meme `{final_title}` vào Kho Vector!**\n"
                f"• ✨ **Vibe:** `{vibe}`\n"
                f"• 🏷️ **Tags:** `{', '.join(tags)}`\n"
                f"• 🖼️ **Ảnh:** {url}",
                ephemeral=True
            )
        else:
            await interaction.followup.send("⚠️ Meme này đã có sẵn trong kho lưu trữ!", ephemeral=True)

    # =========================================================================
    # 2. PREFIX COMMANDS ($m meme ...)
    # =========================================================================
    @commands.command(
        name="meme",
        aliases=["m", "haihuoc", "anhche", "gif"],
        help="Gửi meme theo ngữ cảnh, cảm xúc hoặc câu chuyện"
    )
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    async def meme_prefix(self, ctx: commands.Context, *, prompt_arg: Optional[str] = None):
        if not prompt_arg:
            from bot_instance import send_bot_help
            await send_bot_help(ctx, feature="meme")
            return

        arg_lower = prompt_arg.strip().lower()
        if arg_lower in ["random", "rd", "ngaunhien"]:
            meme = await self.meme_manager.get_random_meme()
            if not meme:
                await ctx.reply("⚠️ Kho meme hiện đang trống!", mention_author=False)
                return
            await self.meme_manager.use_meme(meme["id"])
            view = MemeInteractiveView(
                author_id=ctx.author.id,
                meme_manager=self.meme_manager,
                candidates=[meme],
                current_index=0,
                prompt="Meme ngẫu nhiên"
            )
            embed = view.build_embed(ctx.author)
            if ctx.guild:
                try:
                    await ctx.message.delete()
                except Exception:
                    pass
            sent_msg = await ctx.send(embed=embed, view=view)
            view.message = sent_msg
            return

        if arg_lower in ["stats", "thongke", "top"]:
            stats = await self.meme_manager.get_stats()
            embed = discord.Embed(
                title="📊 THỐNG KÊ KHO MEME VECTOR (MEME VAULT)",
                description=(
                    f"• 📦 **Tổng số meme trong kho:** `{stats['total_memes']}`\n"
                    f"• ❤️ **Tổng lượt thả tim:** `{stats['total_likes']}`\n"
                    f"• 🚀 **Tổng lượt sử dụng:** `{stats['total_uses']}`"
                ),
                color=0xF1C40F
            )
            top_list = stats.get("top_memes", [])
            if top_list:
                lines = [
                    f"`#{i+1}` **{m['title']}** — ❤️ {m['likes']} thích • 🚀 {m['uses']} lượt dùng"
                    for i, m in enumerate(top_list)
                ]
                embed.add_field(name="🏆 Top 5 Meme Được Sử Dụng Nhiều Nhất", value="\n".join(lines), inline=False)
            await ctx.reply(embed=embed, mention_author=False)
            return

        # Thực hiện tìm kiếm meme thông minh
        await self._execute_meme_search(prompt=prompt_arg, user=ctx.author, ctx=ctx)

    # =========================================================================
    # 3. MESSAGE CONTEXT MENUS (Chuột phải vào tin nhắn chat)
    # =========================================================================
    async def context_menu_react_meme(self, interaction: discord.Interaction, message: discord.Message):
        """Context Menu: Đọc nội dung tin nhắn và tự động gửi meme phản hồi thích đáng."""
        content = message.clean_content.strip()
        if not content and not message.attachments:
            await interaction.response.send_message("⚠️ Tin nhắn này không có nội dung chữ hoặc hình ảnh để phân tích!", ephemeral=True)
            return

        prompt = f"Phản hồi lại tin nhắn của {message.author.display_name}: '{content}'"
        await self._execute_meme_search(
            prompt=prompt,
            user=interaction.user,
            chat_context=f"Tin nhắn gốc từ {message.author.display_name}: {content}",
            interaction=interaction
        )

    async def context_menu_save_meme(self, interaction: discord.Interaction, message: discord.Message):
        """Context Menu: Tải ảnh/GIF từ tin nhắn và tự động lưu vào Kho Meme Vector."""
        image_url = None
        if message.attachments:
            for att in message.attachments:
                if any(att.filename.lower().endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                    image_url = att.url
                    break

        if not image_url and message.embeds:
            for emb in message.embeds:
                if emb.image and emb.image.url:
                    image_url = emb.image.url
                    break
                elif emb.thumbnail and emb.thumbnail.url:
                    image_url = emb.thumbnail.url
                    break

        if not image_url:
            await interaction.response.send_message("⚠️ Không tìm thấy tệp ảnh hoặc GIF nào trong tin nhắn này!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        analysis = await MemeAI.analyze_image_with_vision(image_url)
        title = analysis.get("title", f"Meme đóng góp từ {message.author.display_name}")
        vibe = analysis.get("vibe", "Hài hước")
        caption = analysis.get("caption", "Meme được lưu từ kênh chat")
        tags = analysis.get("tags", ["chat_reaction", "meme"])

        text_to_embed = f"Title: {title}. Vibe: {vibe}. Tags: {', '.join(tags)}. Caption: {caption}"
        vector = await MemeAI.get_embedding(text_to_embed)

        saved_id = await self.meme_manager.add_meme(
            title=title,
            url=image_url,
            media_type="gif" if ".gif" in image_url.lower() else "image",
            caption=caption,
            tags=tags,
            vibe=vibe,
            vector=vector,
            source="chat_context_save",
            added_by=interaction.user.display_name
        )

        if saved_id:
            await interaction.followup.send(
                f"🎉 **Đã lưu thành công meme vào Kho Vector!**\n"
                f"• 🎭 **Tên meme:** `{title}`\n"
                f"• ✨ **Vibe:** `{vibe}`\n"
                f"• 🏷️ **Tags:** `{', '.join(tags)}`",
                ephemeral=True
            )
        else:
            await interaction.followup.send("⚠️ Meme này đã có sẵn trong kho lưu trữ!", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MemeCog(bot))
