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


class SummaryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
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


bot = SummaryBot()
