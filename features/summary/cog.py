import sys
import re
import traceback
from typing import Optional, Union, Tuple
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord.ext import commands

import config
from features.summary import ai_summary
from core.ai import split_text


def parse_date_str(date_str: str) -> Optional[Tuple[int, int, int]]:
    """
    Phân tích chuỗi ngày sang (năm, tháng, ngày).
    Hỗ trợ: DD/MM/YYYY, DD/MM/YY, DD/M/YYYY, D/M/YYYY, DD-MM-YYYY, YYYY-MM-DD, YYYY/MM/DD, DD/MM.
    """
    s = date_str.strip()
    # Format YYYY-MM-DD hoặc YYYY/MM/DD
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        y, mon, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime(y, mon, d)
            return (y, mon, d)
        except ValueError:
            return None

    # Format DD/MM/YYYY hoặc DD-MM-YYYY hoặc DD/MM/YY hoặc DD-MM-YY hoặc DD/MM
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?$", s)
    if m:
        d = int(m.group(1))
        mon = int(m.group(2))
        y_str = m.group(3)
        if y_str is None:
            now_vn = datetime.now(timezone(timedelta(hours=7)))
            y = now_vn.year
        elif len(y_str) == 2:
            y = 2000 + int(y_str)
        else:
            y = int(y_str)
        try:
            datetime(y, mon, d)
            return (y, mon, d)
        except ValueError:
            return None

    return None


def parse_time_str(time_str: str) -> Optional[Tuple[int, int, int]]:
    """
    Phân tích chuỗi giờ sang (giờ, phút, giây).
    Hỗ trợ: HH:MM:SS, HH:MM, H:MM, H:M, HHhMM, HHh, Hh, HH (0-23).
    """
    s = time_str.strip().lower()
    # Format HH:MM:SS
    m = re.match(r"^(\d{1,2}):(\d{1,2}):(\d{1,2})$", s)
    if m:
        h, mn, sec = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 0 <= h <= 23 and 0 <= mn <= 59 and 0 <= sec <= 59:
            return (h, mn, sec)
        return None

    # Format HH:MM
    m = re.match(r"^(\d{1,2}):(\d{1,2})$", s)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return (h, mn, 0)
        return None

    # Format HHh hoặc HHhMM (ví dụ 4h, 12h30, 0h)
    m = re.match(r"^(\d{1,2})h(?:(\d{1,2}))?$", s)
    if m:
        h = int(m.group(1))
        mn = int(m.group(2)) if m.group(2) else 0
        if 0 <= h <= 23 and 0 <= mn <= 59:
            return (h, mn, 0)
        return None

    # Số nguyên thuần túy chỉ giờ (ví dụ "0", "4", "12")
    if s.isdigit():
        h = int(s)
        if 0 <= h <= 23:
            return (h, 0, 0)

    return None


def parse_message_anchor(message_input: str) -> Optional[int]:
    """
    Trích xuất Message ID từ Message Link của Discord hoặc từ chuỗi ID thuần túy.
    """
    s = message_input.strip()
    ids = re.findall(r"\d{17,20}", s)
    if ids:
        return int(ids[-1])
    return None


def parse_scan_time_filter(
    date_str: Optional[str] = None,
    from_time_str: Optional[str] = None,
    to_time_str: Optional[str] = None
) -> Tuple[Optional[datetime], Optional[datetime], Optional[str], Optional[str]]:
    """
    Phân tích bộ lọc thời gian ngày/giờ (theo Giờ Việt Nam GMT+7) sang UTC datetime.
    Trả về: (start_time_utc, end_time_utc, scan_info_str, error_message).
    """
    vn_tz = timezone(timedelta(hours=7))
    now_vn = datetime.now(vn_tz)

    if not date_str and not from_time_str and not to_time_str:
        return None, None, None, None

    # Parse date
    if date_str:
        parsed_date = parse_date_str(date_str)
        if not parsed_date:
            return None, None, None, f"Định dạng ngày không hợp lệ: `{date_str}`. Ví dụ đúng: `19/05/2024` hoặc `19/05/24`."
        y, mon, d = parsed_date
    else:
        y, mon, d = now_vn.year, now_vn.month, now_vn.day

    # Parse from_time
    if from_time_str:
        parsed_from = parse_time_str(from_time_str)
        if not parsed_from:
            return None, None, None, f"Định dạng giờ bắt đầu không hợp lệ: `{from_time_str}`. Ví dụ đúng: `00:00` hoặc `0h`."
        f_h, f_m, f_s = parsed_from
    else:
        f_h, f_m, f_s = (0, 0, 0)

    # Parse to_time
    if to_time_str:
        parsed_to = parse_time_str(to_time_str)
        if not parsed_to:
            return None, None, None, f"Định dạng giờ kết thúc không hợp lệ: `{to_time_str}`. Ví dụ đúng: `04:00` hoặc `4h`."
        t_h, t_m, t_s = parsed_to
    else:
        t_h, t_m, t_s = (23, 59, 59)

    try:
        start_vn = datetime(y, mon, d, f_h, f_m, f_s, tzinfo=vn_tz)
        end_vn = datetime(y, mon, d, t_h, t_m, t_s, tzinfo=vn_tz)
    except Exception as e:
        return None, None, None, f"Thời gian không hợp lệ: {e}"

    # Xử lý khung giờ qua đêm (ví dụ từ 23:00 đến 04:00 sáng hôm sau)
    if end_vn <= start_vn:
        if to_time_str:
            end_vn = end_vn + timedelta(days=1)
        else:
            return None, None, None, "Thời gian kết thúc phải sau thời gian bắt đầu!"

    start_utc = start_vn.astimezone(timezone.utc)
    end_utc = end_vn.astimezone(timezone.utc)

    date_display = f"{d:02d}/{mon:02d}/{y}"
    if from_time_str or to_time_str:
        if end_vn.day != start_vn.day:
            scan_info = f"từ {f_h:02d}:{f_m:02d} ngày {date_display} đến {t_h:02d}:{t_m:02d} ngày {end_vn.strftime('%d/%m/%Y')}"
        else:
            scan_info = f"ngày {date_display} ({f_h:02d}:{f_m:02d} ➔ {t_h:02d}:{t_m:02d})"
    else:
        scan_info = f"cả ngày {date_display}"

    return start_utc, end_utc, scan_info, None


class SummaryCog(commands.Cog):
    """Cog xử lý toàn bộ các Slash Command liên quan đến Tóm tắt AI (/tomtat, /test_tomtat)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _validate_inputs(
        self,
        interaction: Optional[discord.Interaction] = None,
        ctx: Optional[commands.Context] = None,
        hours: Optional[float] = None,
        limit: Optional[int] = None,
        date: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        message_link: Optional[str] = None
    ) -> tuple[bool, Optional[datetime], Optional[datetime], Optional[str], Optional[int]]:
        """
        Kiểm tra và chuẩn hóa các tham số đầu vào.
        Trả về (is_valid, start_utc, end_utc, time_scan_info, after_message_id).
        """
        async def reply_error(msg_text: str):
            if interaction:
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg_text, ephemeral=True)
                else:
                    await interaction.followup.send(msg_text, ephemeral=True)
            elif ctx:
                await ctx.reply(msg_text, mention_author=False)

        if config.is_shutting_down:
            await reply_error("❌ Bot đang được cập nhật hoặc tái khởi động hệ thống. Vui lòng thực hiện lại sau 15-30 giây!")
            return False, None, None, None, None

        if limit is not None and (limit <= 0 or limit > config.MAX_FETCH_MESSAGES_LIMIT):
            await reply_error(f"❌ Số lượng tin nhắn quét phải lớn hơn 0 và không được vượt quá {config.MAX_FETCH_MESSAGES_LIMIT} tin nhắn!")
            return False, None, None, None, None

        # Parse & Validate Date/Time Filter
        start_utc, end_utc, time_scan_info, time_err = parse_scan_time_filter(date, from_time, to_time)
        if time_err:
            await reply_error(f"❌ {time_err}")
            return False, None, None, None, None

        # Parse & Validate Message Link / Anchor
        after_message_id = None
        if message_link:
            after_message_id = parse_message_anchor(message_link)
            if not after_message_id:
                await reply_error(f"❌ Không tìm thấy Message ID hợp lệ trong link: `{message_link}`.")
                return False, None, None, None, None

        # Validate hours if not using date/time or message_link
        if start_utc is None and after_message_id is None and hours is not None:
            if hours <= 0 or hours > 168.0:
                await reply_error("❌ Số giờ quét phải lớn hơn 0 và không được vượt quá 168.0 giờ (7 ngày)!")
                return False, None, None, None, None

        return True, start_utc, end_utc, time_scan_info, after_message_id

    @staticmethod
    def _resolve_scan_parameters(
        hours: Optional[float] = None,
        limit: Optional[int] = None,
        time_scan_info: Optional[str] = None,
        after_message_id: Optional[int] = None
    ) -> tuple[Optional[float], int, str]:
        """Quyết định số lượng tin quét và chuỗi thông tin quét (scan_info) cho AI."""
        # Trường hợp 1: Quét theo Ngày & Giờ cụ thể
        if time_scan_info is not None:
            info = f"{time_scan_info}"
            if limit is not None:
                info += f" | tối đa {limit} tin"
            return None, limit, info

        # Trường hợp 2: Quét theo Link Tin Nhắn / Message ID
        if after_message_id is not None:
            lim = limit if limit is not None else 1000
            info = f"từ tin nhắn ID `{after_message_id}` (tối đa {lim} tin)"
            return None, lim, info

        # Trường hợp 3: Quét theo số giờ gần nhất (hoặc limit)
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
    async def _fetch_messages(
        target_channel: discord.TextChannel,
        hours: Optional[float] = None,
        limit: Optional[int] = None,
        start_time_utc: Optional[datetime] = None,
        end_time_utc: Optional[datetime] = None,
        after_message_id: Optional[int] = None
    ) -> tuple[list[str], str]:
        """
        Thu thập tin nhắn từ kênh Discord:
        - Nếu có start_time_utc / end_time_utc: Discord API nhảy thẳng đến timestamp đó (Snowflake index) và lấy trọn vẹn toàn bộ khung giờ (nếu limit=None).
        - Nếu có after_message_id: Bắt đầu lấy từ tin nhắn đó trở đi theo thứ tự xuôi.
        - Nếu có hours: Quét lùi từ hiện tại về quá khứ.
        """
        weekday_map = {0: "T2", 1: "T3", 2: "T4", 3: "T5", 4: "T6", 5: "T7", 6: "CN"}
        vn_tz = timezone(timedelta(hours=7))
        raw_items = []

        # Trường hợp 1: Quét theo khoảng thời gian cụ thể (after/before UTC)
        # Nếu limit=None, Discord API sẽ stream lấy toàn bộ 100% tin nhắn trong khung giờ đó không giới hạn
        if start_time_utc is not None or end_time_utc is not None:
            fetch_after = start_time_utc - timedelta(seconds=1) if start_time_utc else None
            fetch_before = end_time_utc + timedelta(seconds=1) if end_time_utc else None
            async for msg in target_channel.history(limit=limit, after=fetch_after, before=fetch_before, oldest_first=True):
                if msg.author.bot:
                    continue
                local_dt = msg.created_at.astimezone(vn_tz)
                weekday_str = weekday_map[local_dt.weekday()]
                local_time_str = local_dt.strftime('%d/%m %H:%M')
                raw_items.append((msg.created_at, local_dt, f"[{weekday_str} {local_time_str}] {msg.author.display_name}: {msg.content}"))

        # Trường hợp 2: Quét từ một Message ID / Link cụ thể
        elif after_message_id is not None:
            fetch_after = discord.Object(id=after_message_id - 1)
            async for msg in target_channel.history(limit=limit, after=fetch_after, oldest_first=True):
                if msg.author.bot:
                    continue
                local_dt = msg.created_at.astimezone(vn_tz)
                weekday_str = weekday_map[local_dt.weekday()]
                local_time_str = local_dt.strftime('%d/%m %H:%M')
                raw_items.append((msg.created_at, local_dt, f"[{weekday_str} {local_time_str}] {msg.author.display_name}: {msg.content}"))

        # Trường hợp 3: Quét theo số giờ hoặc số lượng tin nhắn gần nhất
        else:
            cutoff_time_utc = None
            if hours is not None:
                now_utc = datetime.now(timezone.utc)
                cutoff_time_utc = now_utc - timedelta(hours=hours)

            async for msg in target_channel.history(limit=limit):
                if cutoff_time_utc and msg.created_at < cutoff_time_utc:
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

    async def _execute_summary_flow(
        self,
        user: Union[discord.User, discord.Member],
        target_channel: discord.TextChannel,
        hours: Optional[float] = None,
        limit: Optional[int] = None,
        date: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        message_link: Optional[str] = None,
        summary_type: str = "short",
        focus: Optional[str] = None,
        send_to_dm: bool = False,
        interaction: Optional[discord.Interaction] = None,
        ctx: Optional[commands.Context] = None
    ):
        """Quy trình thực thi tóm tắt tin nhắn bằng AI dùng chung cho Slash và Prefix Command."""
        is_valid, start_utc, end_utc, time_scan_info, after_message_id = await self._validate_inputs(
            interaction=interaction,
            ctx=ctx,
            hours=hours,
            limit=limit,
            date=date,
            from_time=from_time,
            to_time=to_time,
            message_link=message_link
        )
        if not is_valid:
            return

        followup_msg = None
        if interaction:
            # Nếu gửi qua DM, defer dạng ephemeral để bảo đảm tính riêng tư tuyệt đối trên server
            await interaction.response.defer(ephemeral=send_to_dm)
            config.active_interactions.add(interaction)

        resolved_hours, resolved_limit, scan_info = self._resolve_scan_parameters(
            hours=hours,
            limit=limit,
            time_scan_info=time_scan_info,
            after_message_id=after_message_id
        )

        clean_focus = None
        if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
            clean_focus = focus.strip()

        print(f"📥 [Lệnh nhận] tomtat được gọi bởi @{user.display_name} tại kênh #{target_channel.name}", flush=True)
        print(f"   ↳ Tham số quét: scan_info='{scan_info}', limit={resolved_limit}, kiểu='{summary_type}', focus='{clean_focus}', send_to_dm={send_to_dm}", flush=True)

        mode_info = "Tóm tắt ngắn gọn" if summary_type == "short" else "Tóm tắt dài & Timeline chi tiết"
        focus_info = f" | Tập trung: `{clean_focus}`" if clean_focus else ""
        dm_dest_info = " (Kết quả sẽ gửi qua DM riêng)" if send_to_dm else ""
        loading_text = f"⏳ Đang thu thập và phân tích dữ liệu tại {target_channel.mention} ({scan_info} | chế độ: *{mode_info}*{focus_info}){dm_dest_info}. Vui lòng đợi một lát..."

        if interaction:
            followup_msg = await interaction.followup.send(loading_text, ephemeral=send_to_dm)
        elif ctx:
            followup_msg = await ctx.reply(loading_text, mention_author=False)

        try:
            print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
            raw_messages, time_range_str = await self._fetch_messages(
                target_channel=target_channel,
                hours=resolved_hours,
                limit=resolved_limit,
                start_time_utc=start_utc,
                end_time_utc=end_utc,
                after_message_id=after_message_id
            )
        except Exception as fetch_error:
            print(f"❌ Lỗi khi tải lịch sử chat: {fetch_error}", flush=True)
            traceback.print_exc(file=sys.stdout)
            err_msg = "❌ Không thể tải lịch sử kênh chat. Hãy kiểm tra quyền hạn của bot!"
            if interaction:
                await interaction.followup.send(err_msg, ephemeral=send_to_dm)
                config.active_interactions.discard(interaction)
            elif ctx and followup_msg:
                await followup_msg.edit(content=err_msg)
            return

        print(f"✅ Đã tải xong: Đọc được {len(raw_messages)} tin nhắn ({time_range_str}).", flush=True)

        if not raw_messages:
            print(f"⚠️ Hủy bỏ: Không tìm thấy tin nhắn nào trong kênh #{target_channel.name} để tóm tắt.", flush=True)
            err_msg = f"❌ Không tìm thấy tin nhắn nào thỏa mãn điều kiện quét ({scan_info}) tại kênh {target_channel.mention}."
            if interaction:
                await interaction.followup.send(err_msg, ephemeral=send_to_dm)
                config.active_interactions.discard(interaction)
            elif ctx and followup_msg:
                await followup_msg.edit(content=err_msg)
            return

        try:
            summary_result = await ai_summary.generate_summary(raw_messages, summary_type, clean_focus, scan_info)

            title_str = "📝 TÓM TẮT CHI TIẾT & TIMELINE" if summary_type == "long" else "📝 TÓM TẮT CUỘC TRÒ CHUYỆN"
            embed_color = discord.Color.blue() if summary_type == "long" else discord.Color.green()

            chunks = split_text(summary_result, limit=config.DISCORD_EMBED_CHAR_LIMIT)

            focus_part = f" • Focus: `{clean_focus}`" if clean_focus else ""
            config_header = f"⚙️ `{len(raw_messages)} tin nhắn` ({time_range_str}) • `{scan_info}` • **{mode_info}**{focus_part}\n\n"

            # Gửi thẳng về DM riêng tư của người dùng
            if send_to_dm:
                try:
                    guild_name = target_channel.guild.name if hasattr(target_channel, 'guild') and target_channel.guild else "Server"
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
                        embed.set_footer(text=f"Tóm tắt riêng tư từ #{target_channel.name} ({guild_name}) • Yêu cầu bởi {user.display_name}")

                        content = f"🔒 **[Nội dung tóm tắt riêng tư từ #{target_channel.name}]**" if i == 0 else None
                        await user.send(content=content, embed=embed)

                    success_note = f"✅ **Đã gửi toàn bộ {len(chunks)} bản tóm tắt vào tin nhắn riêng (DM) của bạn!** Vui lòng kiểm tra hộp thư DM."
                    if interaction:
                        await interaction.followup.send(success_note, ephemeral=True)
                    elif ctx:
                        await ctx.reply(success_note, mention_author=False)

                    print(f"🎉 Tóm tắt thành công! Đã gửi {len(chunks)} Embed vào DM của @{user.display_name}.", flush=True)

                except discord.Forbidden:
                    dm_err_msg = (
                        "❌ **Không thể gửi tin nhắn riêng (DM)!**\n"
                        "Có vẻ như bạn đã tắt quyền nhận DM từ thành viên máy chủ này hoặc đã chặn bot.\n"
                        "👉 Vui lòng vào *Cài đặt Discord ➔ Quyền riêng tư & An toàn (Privacy & Safety)* và bật *Cho phép tin nhắn trực tiếp từ thành viên máy chủ (Direct Messages)* rồi thử lại."
                    )
                    if interaction:
                        await interaction.followup.send(dm_err_msg, ephemeral=True)
                    elif ctx:
                        await ctx.reply(dm_err_msg, mention_author=False)
                except Exception as dm_e:
                    print(f"❌ Lỗi gửi DM: {dm_e}", flush=True)
                    err_msg = f"❌ Không thể gửi tin nhắn riêng do lỗi: {dm_e}"
                    if interaction:
                        await interaction.followup.send(err_msg, ephemeral=True)
                    elif ctx:
                        await ctx.reply(err_msg, mention_author=False)

            # Gửi công khai lên kênh server
            else:
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
                    embed.set_footer(text=f"Yêu cầu bởi {user.display_name}")

                    content = f"🔔 {user.mention} Đã tóm tắt xong cuộc trò chuyện!" if i == 0 else None
                    if interaction:
                        await interaction.followup.send(content=content, embed=embed)
                    elif ctx:
                        await ctx.channel.send(content=content, embed=embed)

                print(f"🎉 Tóm tắt thành công! Đã gửi {len(chunks)} Embed tới kênh #{target_channel.name}.", flush=True)

            config.summary_count += 1

            # Ghi nhận hoạt động vào Live Activity Logger
            try:
                from core.activity_logger import activity_logger
                user_avatar = user.display_avatar.url if user.display_avatar else None
                guild_name_str = target_channel.guild.name if hasattr(target_channel, 'guild') and target_channel.guild else "Direct Message"
                guild_id_val = target_channel.guild.id if hasattr(target_channel, 'guild') and target_channel.guild else None
                activity_logger.log(
                    action_type="summary",
                    action_name=f"Tóm tắt: {summary_type.upper()}",
                    user_id=user.id,
                    user_name=user.display_name,
                    user_avatar=user_avatar,
                    guild_name=guild_name_str,
                    guild_id=guild_id_val,
                    channel_name=getattr(target_channel, 'name', 'Unknown'),
                    channel_id=target_channel.id,
                    prompt=f"Phạm vi: {scan_info} | Focus: {clean_focus or '(Không)'} | Chế độ: {summary_type}",
                    response=summary_result,
                    status="success",
                    details={
                        "mode": summary_type,
                        "scan_info": scan_info,
                        "focus": clean_focus,
                        "message_count": len(raw_messages) if 'raw_messages' in locals() else 0
                    }
                )
            except Exception as act_err:
                print(f"⚠️ [ActivityLogger] Lỗi ghi nhận Summary: {act_err}", flush=True)

            if followup_msg and not send_to_dm:
                try:
                    await followup_msg.delete()
                except Exception:
                    pass

        except Exception as e:
            print(f"❌ Lỗi trong quá trình xử lý AI của tomtat: {e}", flush=True)
            traceback.print_exc(file=sys.stdout)
            err_msg = "❌ Đã xảy ra lỗi trong quá trình AI xử lý dữ liệu!"

            # Ghi nhận lỗi vào Activity Logger
            try:
                from core.activity_logger import activity_logger
                user_avatar = user.display_avatar.url if user.display_avatar else None
                guild_name_str = target_channel.guild.name if hasattr(target_channel, 'guild') and target_channel.guild else "Direct Message"
                activity_logger.log(
                    action_type="summary",
                    action_name=f"Tóm tắt (Thất bại)",
                    user_id=user.id,
                    user_name=user.display_name,
                    user_avatar=user_avatar,
                    guild_name=guild_name_str,
                    guild_id=target_channel.guild.id if hasattr(target_channel, 'guild') and target_channel.guild else None,
                    channel_name=getattr(target_channel, 'name', 'Unknown'),
                    channel_id=target_channel.id,
                    prompt=f"Quét: {scan_info}",
                    response=f"Lỗi: {e}",
                    status="error"
                )
            except Exception:
                pass
            if interaction:
                try:
                    await interaction.followup.send(err_msg, ephemeral=send_to_dm)
                except Exception:
                    pass
            elif ctx and followup_msg:
                try:
                    await followup_msg.edit(content=err_msg)
                except Exception:
                    pass

        finally:
            if interaction:
                config.active_interactions.discard(interaction)

    @app_commands.command(name="tomtat", description="Tóm tắt nội dung cuộc trò chuyện trong kênh chat bằng AI")
    @app_commands.describe(
        channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
        hours="Quét tin nhắn trong X giờ qua (Ví dụ: 2.0)",
        date="Quét theo ngày cụ thể (Ví dụ: 19/05/2024 hoặc 19/05/24)",
        from_time="Giờ bắt đầu quét (Ví dụ: 00:00 hoặc 0h)",
        to_time="Giờ kết thúc quét (Ví dụ: 04:00 hoặc 4h)",
        message_link="Link tin nhắn Discord hoặc Message ID để bắt đầu quét",
        limit="Giới hạn số lượng tin nhắn quét tối đa (Ví dụ: 300)",
        summary_type="Kiểu tóm tắt: Ngắn gọn hoặc Chi tiết kèm Timeline",
        focus="Chủ đề hoặc từ khóa cần tập trung phân tích sâu",
        send_to_dm="Gửi kết quả riêng vào DM của bạn thay vì đăng lên kênh chung"
    )
    @app_commands.choices(summary_type=[
        app_commands.Choice(name="Tóm tắt ngắn gọn (Mặc định)", value="short"),
        app_commands.Choice(name="Tóm tắt dài & Timeline chi tiết", value="long")
    ])
    @app_commands.checks.cooldown(1, config.COMMAND_COOLDOWN_SECONDS, key=lambda i: i.user.id)
    async def tomtat(
        self,
        interaction: discord.Interaction,
        channel: Optional[discord.TextChannel] = None,
        hours: Optional[float] = None,
        date: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        message_link: Optional[str] = None,
        limit: Optional[int] = None,
        summary_type: str = "short",
        focus: Optional[str] = None,
        send_to_dm: bool = False
    ):
        target_channel = channel or interaction.channel
        await self._execute_summary_flow(
            user=interaction.user,
            target_channel=target_channel,
            hours=hours,
            limit=limit,
            date=date,
            from_time=from_time,
            to_time=to_time,
            message_link=message_link,
            summary_type=summary_type,
            focus=focus,
            send_to_dm=send_to_dm,
            interaction=interaction
        )

    @commands.command(
        name="tomtat",
        aliases=["summary", "tt"],
        help="Tóm tắt nội dung cuộc trò chuyện trong kênh chat bằng AI"
    )
    @commands.cooldown(1, config.COMMAND_COOLDOWN_SECONDS, commands.BucketType.user)
    async def tomtat_prefix(self, ctx: commands.Context, *args):
        date_str = None
        from_time_str = None
        to_time_str = None
        message_link_str = None
        hours = None
        limit = None
        summary_type = "short"
        focus = None
        send_to_dm = False

        unprocessed = []
        for arg in args:
            arg_clean = arg.strip().lower()
            if arg_clean in ["dm", "inbox", "private", "rieng", "pm"]:
                send_to_dm = True
            elif arg_clean in ["short", "ngan", "ngan-gon", "s"]:
                summary_type = "short"
            elif arg_clean in ["long", "dai", "chi-tiet", "detail", "l"]:
                summary_type = "long"
            elif parse_message_anchor(arg) and ("discord.com" in arg.lower() or len(arg.strip()) >= 17):
                message_link_str = arg.strip()
            elif parse_date_str(arg):
                date_str = arg.strip()
            elif parse_time_str(arg) and from_time_str is None and not arg_clean.endswith("h"):
                from_time_str = arg.strip()
            elif parse_time_str(arg) and from_time_str is not None and to_time_str is None and not arg_clean.endswith("h"):
                to_time_str = arg.strip()
            elif arg_clean.endswith("h") and arg_clean[:-1].replace(".", "", 1).isdigit():
                if date_str is not None and from_time_str is None:
                    from_time_str = arg_clean
                elif date_str is not None and from_time_str is not None and to_time_str is None:
                    to_time_str = arg_clean
                else:
                    hours = float(arg_clean[:-1])
            elif arg_clean.isdigit() and limit is None and (hours is not None or date_str is not None or message_link_str is not None):
                limit = int(arg_clean)
            elif arg_clean.replace(".", "", 1).isdigit() and hours is None and date_str is None:
                val = float(arg_clean)
                if val.is_integer() and val > 24 and limit is None:
                    limit = int(val)
                else:
                    hours = val
            elif arg_clean.isdigit() and limit is None:
                limit = int(arg_clean)
            else:
                unprocessed.append(arg)

        if unprocessed:
            focus = " ".join(unprocessed)

        await self._execute_summary_flow(
            user=ctx.author,
            target_channel=ctx.channel,
            hours=hours,
            limit=limit,
            date=date_str,
            from_time=from_time_str,
            to_time=to_time_str,
            message_link=message_link_str,
            summary_type=summary_type,
            focus=focus,
            send_to_dm=send_to_dm,
            ctx=ctx
        )

    @app_commands.command(name="test_tomtat", description="Chạy tóm tắt thử nghiệm kèm AI tự động đánh giá và chấm điểm chất lượng")
    @app_commands.describe(
        channel="Kênh chat cần tóm tắt (Mặc định là kênh hiện tại)",
        hours="Quét tin nhắn trong X giờ qua (Ví dụ: 24.0)",
        date="Quét theo ngày cụ thể (Ví dụ: 19/05/2024 hoặc 19/05/24)",
        from_time="Giờ bắt đầu quét (Ví dụ: 00:00 hoặc 0h)",
        to_time="Giờ kết thúc quét (Ví dụ: 04:00 hoặc 4h)",
        message_link="Link tin nhắn Discord hoặc Message ID để bắt đầu quét",
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
        channel: Optional[discord.TextChannel] = None,
        hours: Optional[float] = None,
        date: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        message_link: Optional[str] = None,
        limit: Optional[int] = None,
        summary_type: str = "long",
        focus: Optional[str] = None
    ):
        is_valid, start_utc, end_utc, time_scan_info, after_message_id = await self._validate_inputs(
            interaction=interaction,
            hours=hours,
            limit=limit,
            date=date,
            from_time=from_time,
            to_time=to_time,
            message_link=message_link
        )
        if not is_valid:
            return

        await interaction.response.defer(ephemeral=True)
        config.active_interactions.add(interaction)

        target_channel = channel or interaction.channel
        resolved_hours, resolved_limit, scan_info = self._resolve_scan_parameters(
            hours=hours,
            limit=limit,
            time_scan_info=time_scan_info,
            after_message_id=after_message_id
        )

        clean_focus = None
        if focus and focus.strip() and focus.strip().lower() not in ["none", "null", "undefined"]:
            clean_focus = focus.strip()

        print(f"🔬 [Lệnh nhận - Test] /test_tomtat được gọi bởi @{interaction.user.display_name} tại kênh #{target_channel.name}", flush=True)

        try:
            print(f"⏳ Đang tải lịch sử kênh #{target_channel.name}...", flush=True)
            raw_messages, time_range_str = await self._fetch_messages(
                target_channel=target_channel,
                hours=resolved_hours,
                limit=resolved_limit,
                start_time_utc=start_utc,
                end_time_utc=end_utc,
                after_message_id=after_message_id
            )
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
