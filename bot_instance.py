import discord
from discord.ext import commands
import sys
import traceback
from services.config_manager import ConfigManager

intents = discord.Intents.default()
intents.message_content = True

class SummaryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.config_manager = ConfigManager()

    async def setup_hook(self):
        await self.config_manager.init_db()
        try:
            await self.load_extension("cogs.config_cog")
            await self.load_extension("cogs.embed_cog")
            print("Đã tải cogs: config_cog, embed_cog.", flush=True)
        except Exception as cog_error:
            print(f"Lỗi khi tải cog: {cog_error}", flush=True)
            traceback.print_exc(file=sys.stdout)

        print("Dang dong bo hoa Slash Commands...", flush=True)
        try:
            synced = await self.tree.sync()
            print(f"Da dong bo hoa {len(synced)} Slash Commands toan cau thanh cong.", flush=True)
        except Exception as sync_error:
            print(f"Loi khi dong bo hoa Slash Commands: {sync_error}", flush=True)
            traceback.print_exc(file=sys.stdout)

bot = SummaryBot()
