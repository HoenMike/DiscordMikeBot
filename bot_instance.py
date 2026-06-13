import discord
from discord.ext import commands
import sys
import traceback

intents = discord.Intents.default()
intents.message_content = True

class SummaryBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("🔄 Đang đồng bộ hóa Slash Commands...", flush=True)
        try:
            synced = await self.tree.sync()
            print(f"🎉 Đã đồng bộ hóa {len(synced)} Slash Commands toàn cầu thành công!", flush=True)
        except Exception as sync_error:
            print(f"❌ Lỗi khi đồng bộ hóa Slash Commands: {sync_error}", flush=True)
            traceback.print_exc(file=sys.stdout)

bot = SummaryBot()
