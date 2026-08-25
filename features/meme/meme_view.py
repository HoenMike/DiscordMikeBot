import discord
from typing import List, Dict, Optional, Any
from features.meme.manager import MemeManager
from features.meme.ai import MemeAI


class MemeInteractiveView(discord.ui.View):
    """
    View tương tác thông minh dưới mỗi tin nhắn Meme:
    - 🎲 Đổi Meme (Chuyển sang ảnh/GIF tiếp theo)
    - ⭐ Lưu Vào Kho (Auto-Ingest vào Vector Database)
    - 😆 Haha (Tăng lượt Haha cho meme)
    - ❌ Đóng (Xóa tin nhắn gọn gàng)
    """

    def __init__(
        self,
        author_id: int,
        meme_manager: MemeManager,
        candidates: List[Dict[str, Any]],
        current_index: int = 0,
        prompt: str = "",
        ai_data: Optional[Dict[str, Any]] = None,
        timeout: float = 180.0
    ):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.meme_manager = meme_manager
        self.candidates = candidates
        self.current_index = current_index
        self.prompt = prompt
        self.ai_data = ai_data or {}
        self.message: Optional[discord.Message] = None
        self._is_saved = False
        self._likes_count = self.current_meme.get("likes", 0) if self.current_meme else 0
        self._update_buttons()

    @property
    def current_meme(self) -> Optional[Dict[str, Any]]:
        if 0 <= self.current_index < len(self.candidates):
            return self.candidates[self.current_index]
        return None

    def _update_buttons(self):
        self.clear_items()

        # 1. Nút Đổi meme khác
        btn_reroll = discord.ui.Button(
            label="🎲 Đổi Meme",
            style=discord.ButtonStyle.secondary,
            custom_id="meme_btn_reroll",
            disabled=(len(self.candidates) <= 1)
        )
        btn_reroll.callback = self._handle_reroll
        self.add_item(btn_reroll)

        # 2. Nút Lưu vào kho (Nếu chưa được lưu)
        is_already_in_vault = self.current_meme and self.current_meme.get("source") in ["seed", "vault", "user_upload"]
        btn_save = discord.ui.Button(
            label="⭐ Đã Lưu" if (self._is_saved or is_already_in_vault) else "⭐ Lưu Vào Kho",
            style=discord.ButtonStyle.success if (self._is_saved or is_already_in_vault) else discord.ButtonStyle.primary,
            custom_id="meme_btn_save",
            disabled=(self._is_saved or is_already_in_vault)
        )
        btn_save.callback = self._handle_save
        self.add_item(btn_save)

        # 3. Nút Haha
        btn_like = discord.ui.Button(
            label=f"😆 {self._likes_count}" if self._likes_count > 0 else "😆 Haha",
            style=discord.ButtonStyle.secondary,
            custom_id="meme_btn_like"
        )
        btn_like.callback = self._handle_like
        self.add_item(btn_like)

        # 4. Nút Đóng
        btn_close = discord.ui.Button(
            label="❌ Đóng",
            style=discord.ButtonStyle.danger,
            custom_id="meme_btn_close"
        )
        btn_close.callback = self._handle_close
        self.add_item(btn_close)

    def build_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        meme = self.current_meme
        if not meme:
            return discord.Embed(title="❌ Không tìm thấy meme phù hợp!", color=discord.Color.red())

        caption = meme.get("caption") or self.ai_data.get("caption") or f"Tâm trạng: {self.prompt}"
        vibe = meme.get("vibe") or self.ai_data.get("vibe", "Hài hước")
        matched = meme.get("title") or self.ai_data.get("matched_meme", "Meme")

        embed = discord.Embed(
            title=f"🎭 {matched}",
            description=f"💬 *\"{caption}\"*\n\n✨ **Vibe:** `{vibe}`",
            color=0xF1C40F
        )
        embed.set_image(url=meme["url"])

        similarity = meme.get("similarity")
        source = meme.get("source", "web")
        source_label = "⚡ Kho Vector Vault (Hit)" if source in ["seed", "vault"] else "🌐 Khám phá từ Web Search"

        footer_text = f"Yêu cầu bởi {user.display_name} • {source_label}"
        if similarity and similarity < 1.0:
            footer_text += f" (Khớp {int(similarity * 100)}%)"

        embed.set_footer(
            text=footer_text,
            icon_url=user.display_avatar.url if user.display_avatar else None
        )
        return embed

    async def _handle_reroll(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người gọi lệnh mới có thể đổi meme!", ephemeral=True)
            return

        self.current_index = (self.current_index + 1) % len(self.candidates)
        self._is_saved = False
        self._likes_count = self.current_meme.get("likes", 0) if self.current_meme else 0
        self._update_buttons()

        embed = self.build_embed(interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)

    async def _handle_save(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người gọi lệnh mới có thể lưu meme này!", ephemeral=True)
            return

        meme = self.current_meme
        if not meme:
            return

        await interaction.response.defer()

        # Vector hóa và lưu vào DB
        title = meme.get("title") or self.ai_data.get("matched_meme", "Meme người dùng lưu")
        vibe = meme.get("vibe") or self.ai_data.get("vibe", "Hài hước")
        caption = meme.get("caption") or self.ai_data.get("caption", self.prompt)
        tags = [t.lower() for t in self.ai_data.get("vi_keywords", "").split()] + [self.prompt.lower()]

        text_to_embed = f"Title: {title}. Vibe: {vibe}. Tags: {', '.join(tags)}. Caption: {caption}"
        vector = await MemeAI.get_embedding(text_to_embed)

        saved_id = await self.meme_manager.add_meme(
            title=title,
            url=meme["url"],
            media_type=meme.get("media_type", "image"),
            caption=caption,
            tags=tags,
            vibe=vibe,
            vector=vector,
            source="vault",
            added_by=interaction.user.display_name
        )

        if saved_id:
            self._is_saved = True
            self._update_buttons()
            embed = self.build_embed(interaction.user)
            await interaction.edit_original_response(embed=embed, view=self)
            await interaction.followup.send(f"🎉 **Đã lưu thành công meme `{title}` vào Kho Vector!** Lần sau bạn hoặc mọi người hỏi ngữ cảnh này bot sẽ trả lời siêu tốc.", ephemeral=True)
        else:
            await interaction.followup.send("⚠️ Meme này đã có sẵn trong kho lưu trữ!", ephemeral=True)

    async def _handle_like(self, interaction: discord.Interaction):
        meme = self.current_meme
        if not meme or not meme.get("id"):
            # Nếu meme chưa lưu trong DB, tạm thời tăng UI
            self._likes_count += 1
            self._update_buttons()
            await interaction.response.edit_message(view=self)
            return

        is_liked, new_total = await self.meme_manager.like_meme(interaction.user.id, meme["id"])
        self._likes_count = new_total
        self._update_buttons()
        await interaction.response.edit_message(view=self)

    async def _handle_close(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("🔒 Chỉ người gọi lệnh mới có thể đóng tin nhắn!", ephemeral=True)
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
                # Xóa các nút tương tác khi hết thời gian, giữ nguyên ảnh meme
                await self.message.edit(view=None)
            except Exception:
                pass
