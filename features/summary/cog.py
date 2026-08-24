import sys
import re
import traceback
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from features.summary import ai_summary
from core.ai import split_text


class SummaryCog(commands.Cog):
    """Cog xử lý toàn bộ các Slash Command liên quan đến Tóm tắt AI (/tomtat, /test_tomtat)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _validate_inputs(self, interaction: discord.Interaction, hours: float | None, limit: int | None) -> bool:
        if config.is_shutting_down:
            await interaction.response.send_message(
                "❌ Bot đang được cập nhật hoặc tái khởi động hệ thống. Vui lòng thực hiện lại lệnh sau 15-30 giây!",
                ephemeral=True
            )
            return False

        if hours is not None and (hours <= 0 or hours > 168.0):
            await interaction.response.send_message(
                "❌ Số giờ quét phải lớn hơn 0 và không được vượt quá 168.0 giờ (7 ngày)!",
                ephemeral=True
            )
            return False

        if limit is not None and (limit <= 0 or limit > config.MAX_FETCH_MESSAGES_LIMIT):
            await interaction.response.send_message(
                f"❌ Số lượng tin nhắn quét phải lớn hơn 0 và không được vượt quá {config.MAX_FETCH_MESSAGES_LIMIT} tin nhắn!",
                ephemeral=True
            )
            return False

        return True

    @staticmethod
    def _resolve_scan_parameters(hours: float | None, limit: int | None) -> tuple[float | None, int | None, str]:
        if hours is None and limit is None:
            h = config.DEFAULT_SCAN_HOURS
            lim = config.DEFAULT_SCAN_LIMIT
            scan_info = f"{lim} tin nhắn trong {h} giờ qua"
            return h, lim, scan_info
        elif hours is not None and limit is None:
            lim = min(1500, config.MAX_FETCH_MESSAGES_LIMIT)
            scan_info = f"tin nhắn trong {hours} giờ qua"
            return hours, lim, scan_info
        elif limit is not None and hours is None:
            return None, limit, f"{limit} tin nhắn gần nhất"
        else:
            return hours, limit, f"tối đa {limit} tin nhắn trong {hours} giờ qua"

    @staticmethod
    async def _fetch_messages(target_channel: discord.TextChannel, hours: float | None, limit: int | None) -> tuple[list[str], str]:
        weekday_map = {0: "T2", 1: "T3", 2: "T4", 3: "T5", 4: "T6", 5: "T7", 6: "CN"}
        vn_tz = timezone(timedelta(hours=7))
        raw_items = []
        max_limit = min(limit, config.MAX_FETCH_MESSAGES_LIMIT) if limit is not None else 1000

        start_time_utc = None
        if hours is not None:
            now_utc = datetime.now(timezone.utc)
            start_time_utc = now_utc - timedelta(hours=hours)

        async for msg in target_channel.history(limit=max_limit):
            if start_time_utc and msg.created_at < start_time_utc:
                break
            if msg.author.bot:
                continue
            local_dt = msg.created_at.astimezone(vn_tz)
            weekday_str = weekday_map[local_dt.weekday()]
            local_time_str = local_dt.strftime('%d/%m %H:%M')
            raw_items.append((msg.created_at, local_dt, f"[{weekday_str} {local_time_str}] {msg.author.display_name}: {msg.content}"))

        if not raw_items:
            return [], "Không có tin nhắn"

        raw_items.sort(key=lambda x: x[0])
        oldest_dt = raw_items[0][1]
        newest_dt = raw_items[-1][1]
        oldest_str = f"{weekday_map[oldest_dt.weekday()]} {oldest_dt.strftime('%H:%M %d/%m')}"
        newest_str = f"{weekday_map[newest_dt.weekday()]} {newest_dt.strftime('%H:%M %d/%m')}"
        time_range_str = f"{oldest_str} ➔ {newest_str}"

        messages = [item[2] for item in raw_items]
        return messages, time_range_str

    @app_commands.command(name="tomtat", description="Tóm tắt nội dung cuộc trò chuyện trong kênh chat bằng AI")
    @app_commands.describe(
        channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
        hours="Quét tin nhắn trong X giờ qua (Ví dụ: 2.0)",
        limit="Giới hạn số lượng tin nhắn quét tối đa (Ví dụ: 150)",
        summary_type="Kiểu tóm tắt: Ngắn gọn hoặc Chi tiết kèm Timeline",
        focus="Chủ đề hoặc từ khóa cần tập trung phân tích sâu"
    )
    @app_commands.choices(summary_type=[
        app_commands.Choice(name="Tóm tắt ngắn gọn (Mặc định)", value="short"),
        app_commands.Choice(name="Tóm tắt dài & Timeline chi tiết", value="long")
    ])
    @app_commands.checks.cooldown(1, config.COMMAND_COOLDOWN_SECONDS, key=lambda i: i.user.id)
    async def tomtat(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        hours: float = None,
        limit: int = None,
        summary_type: str = "short",
        focus: str = None
    ):
        if not await self._validate_inputs(interaction, hours, limit):
            return

        await interaction.response.defer(ephemeral=False)
        config.active_interactions.add(interaction)

        target_channel = channel or interaction.channel
        resolved_hours, resolved_limit, scan_info = self._resolve_scan_parameters(hours, limit)

        clean_focus = None
        if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
            clean_focus = focus.strip()

        print(f"📥 [Lệnh nhận] /tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)
        print(f"   ↳ Tham số quét: hours={resolved_hours}, limit={resolved_limit}, kiểu='{summary_type}', focus='{clean_focus}'", flush=True)

        mode_info = "Tóm tắt ngắn gọn" if summary_type == "short" else "Tóm tắt dài & Timeline chi tiết"
        focus_info = f" | Tập trung: `{clean_focus}`" if clean_focus else ""
        followup_msg = await interaction.followup.send(
            f"⏳ Đang thu thập và phân tích dữ liệu tại {target_channel.mention} ({scan_info} | chế độ: *{mode_info}*{focus_info}). Vui lòng đợi một lát..."
        )

        try:
            print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
            raw_messages, time_range_str = await self._fetch_messages(target_channel, resolved_hours, resolved_limit)
        except Exception as fetch_error:
            print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
            traceback.print_exc(file=sys.stdout)
            await interaction.followup.send("❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!")
            config.active_interactions.discard(interaction)
            return

        print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn ({time_range_str}).", flush=True)

        if not raw_messages:
            print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
            await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}.")
            config.active_interactions.discard(interaction)
            return

        try:
            summary_result = await ai_summary.generate_summary(raw_messages, summary_type, clean_focus, scan_info)

            title_str = "📝 TÓM TẮT CHI TIẾT & TIMELINE" if summary_type == "long" else "📝 TÓM TẮT CUỘC TRÒ CHUYỆN"
            embed_color = discord.Color.blue() if summary_type == "long" else discord.Color.green()

            chunks = split_text(summary_result, limit=config.DISCORD_EMBED_CHAR_LIMIT)

            # Dòng cấu hình ngắn gọn 1 hàng ngang nằm ngay trên cùng của phần 1
            focus_part = f" • Focus: `{clean_focus}`" if clean_focus else ""
            config_header = f"⚙️ `{len(raw_messages)} tin nhắn` ({time_range_str}) • `{scan_info}` • **{mode_info}**{focus_part}\n\n"

            for i, chunk in enumerate(chunks):
                part_title = title_str
                if len(chunks) > 1:
                    part_title += f" (Phần {i+1}/{len(chunks)})"

                description_text = (config_header + chunk) if i == 0 else chunk

                embed = discord.Embed(
                    title=part_title,
                    description=description_text,
                    color=embed_color
                )

                embed.set_footer(text=f"Yêu cầu bởi {interaction.user.display_name}")

                content = f"🔔 {interaction.user.mention} Đã tóm tắt xong cuộc trò chuyện!" if i == 0 else None
                await interaction.followup.send(content=content, embed=embed)

            print(f"🎉 Tóm tắt thành công! Đã gửi {len(chunks)} Embed tới kênh #{target_channel.name}.", flush=True)
            config.summary_count += 1

            try:
                await followup_msg.delete()
            except Exception:
                pass

        except Exception as e:
            print(f"❌ Lỗi trong quá trình xử lý AI của /tomtat: {e}", flush=True)
            traceback.print_exc(file=sys.stdout)
            try:
                await interaction.followup.send("❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!")
            except Exception:
                pass

        finally:
            config.active_interactions.discard(interaction)

    @app_commands.command(name="test_tomtat", description="Chạy tóm tắt thử nghiệm kèm AI tự động đánh giá và chấm điểm chất lượng")
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
    @app_commands.checks.cooldown(1, config.COMMAND_COOLDOWN_SECONDS, key=lambda i: i.user.id)
    async def test_tomtat(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel = None,
        hours: float = None,
        limit: int = None,
        summary_type: str = "long",
        focus: str = None
    ):
        if not await self._validate_inputs(interaction, hours, limit):
            return

        await interaction.response.defer(ephemeral=True)
        config.active_interactions.add(interaction)

        target_channel = channel or interaction.channel
        resolved_hours, resolved_limit, scan_info = self._resolve_scan_parameters(hours, limit)

        clean_focus = None
        if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
            clean_focus = focus.strip()

        print(f"🔬 [Lệnh nhận - Test] /test_tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)

        try:
            print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
            raw_messages, time_range_str = await self._fetch_messages(target_channel, resolved_hours, resolved_limit)
        except Exception as fetch_error:
            print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
            traceback.print_exc(file=sys.stdout)
            await interaction.followup.send("❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!", ephemeral=True)
            config.active_interactions.discard(interaction)
            return

        print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn ({time_range_str}).", flush=True)

        if not raw_messages:
            print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
            await interaction.followup.send(f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}.", ephemeral=True)
            config.active_interactions.discard(interaction)
            return

        try:
            summary_result = await ai_summary.generate_summary(raw_messages, summary_type, clean_focus, scan_info)

            print("🔬 [Test Command] Đang gửi kết quả cho AI QA tự động chấm điểm...", flush=True)
            raw_history_text = "\n".join(raw_messages)
            evaluation_report = await ai_summary.evaluate_summary(raw_history_text, summary_result, summary_type, clean_focus)

            score_val = "N/A"
            score_match = re.search(r"-\s*\*\*Điểm số\*\*:\s*([\d\.\/\s]+)", evaluation_report, re.IGNORECASE)
            if score_match:
                score_val = score_match.group(1).strip()

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

            try:
                await interaction.delete_original_response()
            except Exception:
                pass

            print(f"🎉 Kiểm thử thành công! Báo cáo test đã được đẩy lên Web Dashboard (Điểm: {score_val}).", flush=True)
            config.summary_count += 1

        except Exception as e:
            print(f"❌ Lỗi trong pha xử lý AI của /test_tomtat: {e}", flush=True)
            traceback.print_exc(file=sys.stdout)
            try:
                await interaction.delete_original_response()
            except Exception:
                pass

        finally:
            config.active_interactions.discard(interaction)

    @tomtat.error
    @test_tomtat.error
    async def summary_error_handler(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            msg = f"⏳ Bạn đang thao tác quá nhanh! Vui lòng đợi {round(error.retry_after, 1)} giây trước khi thử lại."
        else:
            msg = "❌ Đã xảy ra lỗi khi thực thi lệnh!"
            print(f"❌ Lỗi thực thi lệnh tóm tắt: {error}", flush=True)

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(SummaryCog(bot))
