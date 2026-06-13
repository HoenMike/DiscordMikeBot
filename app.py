import config # Khởi tạo log redirection trước
from bot_instance import bot
from web_dashboard import app
import ai_helper

import os
import sys
import logging
import traceback
import discord
from discord import app_commands
from datetime import datetime, timezone, timedelta
import asyncio
import signal
from threading import Thread

# Quản lý trạng thái tắt máy (Graceful Shutdown)
@bot.event
async def on_ready():
    print(f"🎉 Bot tóm tắt đã kết nối thành công: {bot.user}", flush=True)

# Lệnh Slash Command /tomtat
@bot.tree.command(name="tomtat", description="Tóm tắt nội dung cuộc trò chuyện trong một kênh")
@app_commands.describe(
    channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
    hours="Quét tin nhắn trong X giờ qua (Ví dụ: 24.0)",
    limit="Giới hạn số lượng tin nhắn quét tối đa (Ví dụ: 300)",
    summary_type="Kiểu tóm tắt: Ngắn gọn hoặc Chi tiết kèm Timeline",
    focus="Chủ đề hoặc từ khóa cần tập trung phân tích sâu (Ví dụ: drama, lỗi deploy)"
)
@app_commands.choices(summary_type=[
    app_commands.Choice(name="Tóm tắt ngắn gọn (Mặc định)", value="short"),
    app_commands.Choice(name="Tóm tắt dài & Timeline chi tiết", value="long")
])
@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
async def tomtat(
    interaction: discord.Interaction, 
    channel: discord.TextChannel = None, 
    hours: float = None, 
    limit: int = None,
    summary_type: str = "short",
    focus: str = None
):
    if config.is_shutting_down:
        await interaction.response.send_message(
            "❌ Bot đang được cập nhật hoặc tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
            ephemeral=True
        )
        return

    # Kiểm tra giới hạn trị số đầu vào hỗ trợ lên tới 2500 tin nhắn
    if hours is not None and (hours <= 0 or hours > 168.0):
        await interaction.response.send_message(
            "❌ Số giờ quét phải lớn hơn 0 và không được vượt quá 168.0 giờ (7 ngày)!",
            ephemeral=True
        )
        return

    if limit is not None and (limit <= 0 or limit > 2500):
        await interaction.response.send_message(
            "❌ Số lượng tin nhắn quét phải lớn hơn 0 và không được vượt quá 2500 tin nhắn!",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    config.active_interactions.add(interaction)
    
    target_channel = channel or interaction.channel
    
    # Xác định các giá trị mặc định nếu người dùng bỏ trống
    if hours is None and limit is None:
        hours = 2.0
        limit = 150
        scan_info = "150 tin nhắn trong 2.0 giờ qua"
    elif hours is not None and limit is None:
        limit = 1500  # Giới hạn trần an toàn lên 1500 khi lọc theo giờ
        scan_info = f"tin nhắn trong {hours} giờ qua"
    elif limit is not None and hours is None:
        scan_info = f"{limit} tin nhắn gần nhất"
    else:
        scan_info = f"tối đa {limit} tin nhắn trong {hours} giờ qua"

    clean_focus = None
    if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
        clean_focus = focus.strip()

    print(f"📥 [Lệnh nhận] /tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)
    print(f"   ↳ Tham số quét: hours={hours}, limit={limit}, kiểu='{summary_type}', focus='{clean_focus}'", flush=True)

    # Gửi thông báo tạm thời ban đầu
    mode_info = "Tóm tắt ngắn gọn" if summary_type == "short" else "Tóm tắt dài & Timeline chi tiết"
    focus_info = f" | Tập trung: `{clean_focus}`" if clean_focus else ""
    followup_msg = await interaction.followup.send(
        f"⏳ Đang thu thập và phân tích dữ liệu tại {target_channel.mention} ({scan_info} | chế độ: *{mode_info}*{focus_info}). Vui lòng đợi một lát..."
    )

    vn_tz = timezone(timedelta(hours=7))
    raw_messages = []
    
    try:
        print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
        max_limit = min(limit, 2500) if limit is not None else 1000
        
        # Xác định mốc thời gian lọc
        start_time_utc = None
        if hours is not None:
            now_utc = datetime.now(timezone.utc)
            start_time_utc = now_utc - timedelta(hours=hours)
            
        # Quét từ mới nhất trở về trước
        async for msg in target_channel.history(limit=max_limit):
            if start_time_utc and msg.created_at < start_time_utc:
                break
            if msg.author.bot:
                continue
            local_time = msg.created_at.astimezone(vn_tz).strftime('%d/%m %H:%M')
            raw_messages.append((msg.created_at, f"[{local_time}] {msg.author.display_name}: {msg.content}"))
            
        # Sắp xếp lại từ cũ đến mới (trình tự thời gian tăng dần)
        raw_messages.sort(key=lambda x: x[0])
        raw_messages = [item[1] for item in raw_messages]

    except Exception as fetch_error:
        print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
        traceback.print_exc(file=sys.stdout)
        await interaction.followup.send("❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!")
        config.active_interactions.discard(interaction)
        return

    print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn thích hợp.", flush=True)

    if not raw_messages:
        print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
        await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}.")
        config.active_interactions.discard(interaction)
        return

    try:
        # Gọi hàm xử lý AI thông minh (hỗ trợ MapReduce)
        summary_result = await ai_helper.generate_summary(raw_messages, summary_type, clean_focus, scan_info)
        
        title_str = "📝 TÓM TẮT CHI TIẾT & TIMELINE" if summary_type == "long" else "📝 TÓM TẮT CUỘC TRÒ CHUYỆN"
        embed_color = discord.Color.blue() if summary_type == "long" else discord.Color.green()

        # Chia nhỏ kết quả thành nhiều phần nếu vượt quá giới hạn hiển thị của Discord
        chunks = ai_helper.split_text(summary_result, limit=3500)
        
        for i, chunk in enumerate(chunks):
            part_title = title_str
            if len(chunks) > 1:
                part_title += f" (Phần {i+1}/{len(chunks)})"
            
            embed = discord.Embed(
                title=part_title,
                description=chunk,
                color=embed_color
            )
            
            # Đính kèm thông tin cấu hình quét ở phần đầu tiên
            if i == 0:
                embed.add_field(
                    name="⚙️ Cấu hình quét", 
                    value=f"Phạm vi: **{scan_info}** ({len(raw_messages)} tin nhắn thực tế)\nChế độ: **{mode_info}**{f' | Focus: **`{clean_focus}`**' if clean_focus else ''}", 
                    inline=False
                )
            
            embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")
            
            # Tag người dùng đã yêu cầu ở tin nhắn đầu tiên
            content = f"🔔 {interaction.user.mention} Đã tóm tắt xong cuộc trò chuyện!" if i == 0 else None
            await interaction.followup.send(content=content, embed=embed)

        print(f"🎉 Tóm tắt thành công! Đã gửi {len(chunks)} Embed tới kênh #{target_channel.name}.", flush=True)
        config.summary_count += 1
        
        try:
            await followup_msg.delete()
            print("ℹ️ Đã xóa thông báo tạm thời sau khi gửi tóm tắt.", flush=True)
        except Exception as delete_error:
            print(f"⚠️ Không xóa được thông báo tải: {delete_error}", flush=True)

        config.active_interactions.discard(interaction)

    except Exception as e:
        print(f"❌ Lỗi trong quá trình xử lý lệnh /tomtat: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        try:
            await interaction.followup.send("❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!")
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi đến Discord: {send_error}", flush=True)
        config.active_interactions.discard(interaction)

@tomtat.error
async def tomtat_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Bạn đang thao tác quá nhanh! Vui lòng đợi {round(error.retry_after, 1)} giây trước khi thử lại.",
            ephemeral=True
        )
    else:
        print(f"❌ Lỗi khi thực thi Slash Command /tomtat: {error}", flush=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi: {send_error}", flush=True)

# Lệnh Slash Command /test_tomtat
@bot.tree.command(name="test_test_tomtat", description="Tạm thời tránh trùng lặp")
async def dummy_test():
    pass

# Đăng ký lệnh /test_tomtat chính thức
@bot.tree.command(name="test_tomtat", description="Chạy tóm tắt thử nghiệm kèm AI tự động đánh giá và chấm điểm chất lượng")
@app_commands.describe(
    channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
    hours="Quét tin nhắn trong X giờ qua (Ví dụ: 24.0)",
    limit="Giới hạn số lượng tin nhắn quét tối đa (Ví dụ: 100)",
    summary_type="Kiểu tóm tắt: Ngắn gọn hoặc Chi tiết kèm Timeline",
    focus="Chủ đề hoặc từ khóa cần tập trung phân tích sâu"
)
@app_commands.choices(summary_type=[
    app_commands.Choice(name="Tóm tắt ngắn gọn", value="short"),
    app_commands.Choice(name="Tóm tắt dài & Timeline chi tiết", value="long")
])
@app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
async def test_tomtat(
    interaction: discord.Interaction, 
    channel: discord.TextChannel = None, 
    hours: float = None, 
    limit: int = None,
    summary_type: str = "long",
    focus: str = None
):
    if config.is_shutting_down:
        await interaction.response.send_message(
            "❌ Bot đang được cập nhật hoặc tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
            ephemeral=True
        )
        return

    # Kiểm tra giới hạn trị số đầu vào hỗ trợ lên tới 2500 tin nhắn
    if hours is not None and (hours <= 0 or hours > 168.0):
        await interaction.response.send_message(
            "❌ Số giờ quét phải lớn hơn 0 và không được vượt quá 168.0 giờ (7 ngày)!",
            ephemeral=True
        )
        return

    if limit is not None and (limit <= 0 or limit > 2500):
        await interaction.response.send_message(
            "❌ Số lượng tin nhắn quét phải lớn hơn 0 và không được vượt quá 2500 tin nhắn!",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    config.active_interactions.add(interaction)
    
    target_channel = channel or interaction.channel
    
    # Xác định các giá trị mặc định nếu người dùng bỏ trống
    if hours is None and limit is None:
        hours = 2.0
        limit = 150
        scan_info = "150 tin nhắn trong 2.0 giờ qua"
    elif hours is not None and limit is None:
        limit = 1500  # Giới hạn trần an toàn lên 1500 khi lọc theo giờ
        scan_info = f"tin nhắn trong {hours} giờ qua"
    elif limit is not None and hours is None:
        scan_info = f"{limit} tin nhắn gần nhất"
    else:
        scan_info = f"tối đa {limit} tin nhắn trong {hours} giờ qua"

    clean_focus = None
    if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
        clean_focus = focus.strip()

    print(f"🔬 [Lệnh nhận - Test] /test_tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)
    print(f"   ↳ Tham số quét: hours={hours}, limit={limit}, kiểu='{summary_type}', focus='{clean_focus}'", flush=True)

    # Gửi thông báo tạm thời ban đầu
    mode_info = "Tóm tắt ngắn gọn" if summary_type == "short" else "Tóm tắt dài & Timeline chi tiết"
    focus_info = f" | Tập trung: `{clean_focus}`" if clean_focus else ""
    followup_msg = await interaction.followup.send(
        f"🔬 **[Chế độ kiểm thử]** Đang thu thập dữ liệu và chạy phân tích tự động tại {target_channel.mention}...\n"
        f"⚙️ Cấu hình: *{mode_info}*{focus_info} ({scan_info})"
    )

    vn_tz = timezone(timedelta(hours=7))
    raw_messages = []
    
    try:
        print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
        max_limit = min(limit, 2500) if limit is not None else 1000
        
        # Xác định mốc thời gian lọc
        start_time_utc = None
        if hours is not None:
            now_utc = datetime.now(timezone.utc)
            start_time_utc = now_utc - timedelta(hours=hours)
            
        # Quét từ mới nhất trở về trước
        async for msg in target_channel.history(limit=max_limit):
            if start_time_utc and msg.created_at < start_time_utc:
                break
            if msg.author.bot:
                continue
            local_time = msg.created_at.astimezone(vn_tz).strftime('%d/%m %H:%M')
            raw_messages.append((msg.created_at, f"[{local_time}] {msg.author.display_name}: {msg.content}"))
            
        # Sắp xếp lại từ cũ đến mới (trình tự thời gian tăng dần)
        raw_messages.sort(key=lambda x: x[0])
        raw_messages = [item[1] for item in raw_messages]

    except Exception as fetch_error:
        print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
        traceback.print_exc(file=sys.stdout)
        await interaction.followup.send("❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!")
        config.active_interactions.discard(interaction)
        return

    print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn thích hợp.", flush=True)

    if not raw_messages:
        print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
        await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}.")
        config.active_interactions.discard(interaction)
        return

    try:
        # 1. Chạy tóm tắt
        summary_result = await ai_helper.generate_summary(raw_messages, summary_type, clean_focus, scan_info)
        
        # 2. Chạy đánh giá chất lượng bằng AI QA
        print("🔬 [Test Command] Đang gửi kết quả cho AI QA tự động chấm điểm...", flush=True)
        raw_history_text = "\n".join(raw_messages)
        evaluation_report = await ai_helper.evaluate_summary(raw_history_text, summary_result, summary_type, clean_focus)
        
        # Trích xuất điểm số
        import re
        score_val = "N/A"
        score_match = re.search(r"-\s*\*\*Điểm số\*\*:\s*([\d\.\/\s]+)", evaluation_report, re.IGNORECASE)
        if score_match:
            score_val = score_match.group(1).strip()

        # Lưu thông số test vào Dashboard
        test_run = {
            "timestamp": datetime.now(timezone(timedelta(hours=7))).strftime('%d/%m %H:%M:%S'),
            "source": f"Lệnh Discord: #{target_channel.name} ({target_channel.guild.name})",
            "scan_info": scan_info,
            "mode": summary_type,
            "focus": clean_focus,
            "raw_count": len(raw_messages),
            "summary": summary_result,
            "evaluation": evaluation_report,
            "score": score_val
        }
        config.test_runs.insert(0, test_run)
        if len(config.test_runs) > 20:
            config.test_runs = config.test_runs[:20]

        # 3. Gửi thông báo kết quả tối giản lên Discord (không gửi kèm bản tóm tắt hay báo cáo chi tiết)
        await interaction.followup.send(
            f"✅ {interaction.user.mention} **Đã hoàn thành lượt tự đánh giá (Self-Audit) cuộc trò chuyện thành công!**\n"
            f"📊 **Điểm số AI QA chấm**: **{score_val}/10**\n"
            f"🔗 Chi tiết bản tóm tắt và báo cáo phản biện cụ thể đã được cập nhật trực tuyến lên Web Dashboard tại: https://discordmikebot.onrender.com"
        )

        print(f"🎉 Kiểm thử thành công! Báo cáo test đã được đẩy lên Web Dashboard.", flush=True)
        config.summary_count += 1
        
        try:
            await followup_msg.delete()
        except Exception as delete_error:
            print(f"⚠️ Không xóa được thông báo tải: {delete_error}", flush=True)

        config.active_interactions.discard(interaction)

    except Exception as e:
        print(f"❌ Lỗi trong quá trình xử lý lệnh /test_tomtat: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        try:
            await interaction.followup.send("❌ Đã xảy ra lỗi trong quá trình chạy kiểm thử AI!")
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi đến Discord: {send_error}", flush=True)
        config.active_interactions.discard(interaction)

@test_tomtat.error
async def test_tomtat_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Bạn đang thao tác quá nhanh! Vui lòng đợi {round(error.retry_after, 1)} giây trước khi thử lại.",
            ephemeral=True
        )
    else:
        print(f"❌ Lỗi khi thực thi Slash Command /test_tomtat: {error}", flush=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi khi thực thi lệnh!", ephemeral=True)
        except Exception as send_error:
            print(f"⚠️ Không thể gửi thông báo lỗi: {send_error}", flush=True)

# Khởi chạy Discord Bot trong luồng phụ
bot_started = False

@app.before_request
def start_bot_on_first_request():
    global bot_started
    if not bot_started:
        bot_started = True
        print("🚀 [Gunicorn Worker] Nhận request đầu tiên, bắt đầu khởi chạy Discord Bot trong luồng phụ...", flush=True)
        bot_thread = Thread(target=run_discord_bot)
        bot_thread.daemon = True
        bot_thread.start()

def run_discord_bot():
    try:
        print("🤖 Bắt đầu chạy bot.run()...", flush=True)
        bot.run(config.DISCORD_TOKEN)
    except Exception as run_error:
        print(f"❌ Lỗi crash khi chạy bot.run(): {run_error}", flush=True)
        traceback.print_exc(file=sys.stdout)

# GRACEFUL SHUTDOWN HANDLER
async def graceful_shutdown():
    config.is_shutting_down = True
    print("👋 Bắt đầu quy trình tắt bot graceful...", flush=True)
    
    wait_time = 0
    while config.active_interactions and wait_time < 15:
        print(f"⏳ Đang chờ {len(config.active_interactions)} lệnh dở hoàn thành... ({wait_time}s)", flush=True)
        await asyncio.sleep(1)
        wait_time += 1

    if config.active_interactions:
        print(f"⚠️ Hết thời gian chờ. Hủy bỏ {len(config.active_interactions)} lệnh còn lại...", flush=True)
        for interaction in list(config.active_interactions):
            try:
                print(f"   ↳ Gửi thông báo hủy lệnh tới user @{interaction.user.display_name}", flush=True)
                await interaction.followup.send(
                    "❌ Bot đang tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
                    ephemeral=True
                )
            except Exception as e:
                print(f"⚠️ Không thể gửi thông báo shutdown tới user: {e}", flush=True)
    
    try:
        await bot.close()
        print("🔌 Đã đóng kết nối bot Discord thành công.", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi khi đóng bot: {e}", flush=True)

def handle_sigterm(signum, frame):
    if config.is_shutting_down:
        return
    config.is_shutting_down = True
    print(f"📥 Nhận được tín hiệu tắt máy (signal {signum}). Đang tắt máy dọn dẹp...", flush=True)
    
    if bot.loop and bot.loop.is_running():
        future = asyncio.run_coroutine_threadsafe(graceful_shutdown(), bot.loop)
        try:
            future.result(timeout=20)
        except Exception as e:
            print(f"⚠️ Hết thời gian chờ hoặc xảy ra lỗi khi tắt bot: {e}", flush=True)
            
    print("☠️ Tiến trình kết thúc.", flush=True)
    sys.exit(0)

# Đăng ký signal handler
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

if __name__ == "__main__":
    if not bot_started:
        bot_started = True
        print("🚀 [Local Mode] Khởi chạy Discord Bot ngay lập tức...", flush=True)
        bot_thread = Thread(target=run_discord_bot)
        bot_thread.daemon = True
        bot_thread.start()
        
    port = int(os.environ.get("PORT", 8080))
    print(f"ℹ️ Khởi chạy Flask Server trên cổng {port}...", flush=True)
    app.run(host='0.0.0.0', port=port)
