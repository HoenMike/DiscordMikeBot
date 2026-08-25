import asyncio
import io
import os
import re
import tempfile
import uuid
import wave
from typing import Optional, Set
import discord
from google.genai import types

import config
from core.ai import get_ai_client
from features.tarot.deck import READER_STYLES

# Ánh xạ phong cách Reader sang Preset Voice của Gemini 2.0
VOICE_MAP = {
    "neutral": "Charon",  # ⚖️ Orion: Nam trầm ấm, điềm đạm, chín chắn
    "healer": "Aoede",    # 🌸 Celeste: Nữ dịu dàng, ân cần, giàu cảm xúc
    "chaos": "Puck",      # 🃏 Jester: Tinh nghịch, hóm hỉnh, năng động
}

# Tập hợp theo dõi các server đang có luồng đọc bài Voice (tránh xung đột)
_active_voice_guilds: Set[int] = set()


def _clean_markdown_for_tts(text: str) -> str:
    """Loại bỏ các ký tự Markdown, link, tiêu đề để AI đọc trôi chảy, tự nhiên."""
    if not text:
        return ""

    cleaned = text
    # Xóa các định dạng bold, italic, code
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
    cleaned = re.sub(r"[-=]{3,}", " ", cleaned)
    # Thay thế gạch đầu dòng bằng dấu chấm để tạo nhịp ngắt
    cleaned = re.sub(r"^[•\-\*]\s+", "", cleaned, flags=re.MULTILINE)
    # Loại bỏ các emoji rườm rà nhưng giữ lại nội dung chính
    cleaned = re.sub(r"[🎯🃏💡✨🔮🌸⚖️👑🌿⏳🧲⚡]", "", cleaned)
    # Chuẩn hóa khoảng trắng và dòng
    cleaned = re.sub(r"\n{2,}", ". ", cleaned)
    cleaned = re.sub(r"\n", " ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    return cleaned


def pcm_to_wav_bytes(pcm_data: bytes, sample_rate: int = 24000, num_channels: int = 1, sampwidth: int = 2) -> bytes:
    """Đóng gói dữ liệu raw PCM 24kHz 16-bit Mono thành file WAV chuẩn."""
    wav_io = io.BytesIO()
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(num_channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    wav_io.seek(0)
    return wav_io.read()


EDGE_VOICE_CONFIG = {
    "neutral": {"voice": "vi-VN-NamMinhNeural", "pitch": "+0Hz", "rate": "+0%"},
    "healer": {"voice": "vi-VN-HoaiMyNeural", "pitch": "+0Hz", "rate": "-4%"},
    "chaos": {"voice": "vi-VN-NamMinhNeural", "pitch": "+12Hz", "rate": "+15%"},
}


async def generate_speech_edge_tts(clean_text: str, reader_style: str) -> Optional[str]:
    """Tạo file audio siêu tốc (<1.5s) bằng Edge Neural TTS tiếng Việt chuyên dụng."""
    try:
        import edge_tts
        cfg = EDGE_VOICE_CONFIG.get(reader_style, EDGE_VOICE_CONFIG["neutral"])
        temp_dir = tempfile.gettempdir()
        temp_filename = f"tarot_voice_{uuid.uuid4().hex}.mp3"
        temp_path = os.path.join(temp_dir, temp_filename)

        communicate = edge_tts.Communicate(
            text=clean_text,
            voice=cfg["voice"],
            pitch=cfg["pitch"],
            rate=cfg["rate"]
        )
        await communicate.save(temp_path)
        if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
            print(f"✅ [Edge-TTS] Đã tạo file audio giọng '{cfg['voice']}' ({reader_style}) thành công: {temp_path}", flush=True)
            return temp_path
    except Exception as e:
        print(f"⚠️ [Edge-TTS] Gặp lỗi khi tạo audio: {e}", flush=True)
    return None


async def generate_tarot_speech(
    reading_text: str,
    reader_style: str,
    user_name: str,
    spread_name: str = ""
) -> Optional[str]:
    """
    Tạo file âm thanh giọng đọc theo cá tính từng Reader.
    Ưu tiên Edge Neural TTS tiếng Việt cực nhanh và tự nhiên,
    tự động fallback sang Gemini TTS nếu cần.
    """
    clean_text = _clean_markdown_for_tts(reading_text)
    if not clean_text:
        return None

    style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
    reader_name = style_info.get("name", "Reader")

    # 1. Thử tạo âm thanh bằng Edge-TTS (Cực nhanh, mượt mà tiếng Việt, không tốn quota)
    edge_audio_path = await generate_speech_edge_tts(clean_text, reader_style)
    if edge_audio_path:
        return edge_audio_path

    # 2. Fallback: Gemini TTS Multimodal Audio
    voice_name = VOICE_MAP.get(reader_style, "Charon")
    prompt = f"""
Bạn là {reader_name}.
Hãy đọc bài Tarot sau cho {user_name} một cách thật tự nhiên, liền mạch, biểu cảm và đúng tính cách của bạn.
Không thêm các lời chào hỏi ngoài lề, không đọc các ký tự đặc biệt. Hãy đọc trực tiếp nội dung dưới đây:

{clean_text}
""".strip()

    client = get_ai_client()
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name=voice_name
            )
        )
    )

    gen_config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=speech_config,
        temperature=0.7
    )

    models_to_try = getattr(
        config,
        "VOICE_FALLBACK_MODELS",
        ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-pro-preview-tts"]
    )

    ordered_models = []
    for m in models_to_try:
        if m and m not in ordered_models:
            ordered_models.append(m)

    last_error = None
    for model_name in ordered_models:
        try:
            print(f"🎙️ [Tarot Voice] Đang tạo giọng đọc '{reader_name}' ({voice_name}) bằng model '{model_name}'...", flush=True)
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=model_name,
                    contents=prompt,
                    config=gen_config
                ),
                timeout=35.0
            )

            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.data:
                    raw_audio_data = part.inline_data.data
                    mime_type = getattr(part.inline_data, "mime_type", "")

                    temp_dir = tempfile.gettempdir()
                    temp_filename = f"tarot_voice_{uuid.uuid4().hex}.wav"
                    temp_path = os.path.join(temp_dir, temp_filename)

                    if "wav" in mime_type.lower():
                        with open(temp_path, "wb") as f:
                            f.write(raw_audio_data)
                    else:
                        wav_bytes = pcm_to_wav_bytes(raw_audio_data, sample_rate=24000)
                        with open(temp_path, "wb") as f:
                            f.write(wav_bytes)

                    print(f"✅ [Tarot Voice] Đã tạo file audio thành công: {temp_path}", flush=True)
                    return temp_path

        except asyncio.TimeoutError:
            print(f"⏱️ [Tarot Voice] Model '{model_name}' timeout (>35s), thử model tiếp theo...", flush=True)
        except Exception as e:
            last_error = e
            print(f"⚠️ [Tarot Voice] Model '{model_name}' gặp lỗi: {e}", flush=True)

    print(f"❌ [Tarot Voice] Không thể tạo giọng đọc Audio. Lỗi cuối: {last_error}", flush=True)
    return None


async def play_tarot_voice(
    interaction: discord.Interaction,
    reading_text: str,
    reader_style: str,
    spread_name: str = ""
):
    """
    Xử lý toàn bộ quy trình:
    1. Kiểm tra trạng thái Voice của người dùng.
    2. Kết nối vào Voice Channel.
    3. Tạo file Audio và phát qua FFmpeg.
    4. Tự động ngắt kết nối và dọn dẹp file tạm.
    """
    # 1. Kiểm tra xem user có đang ở trong Voice Channel không
    user_voice = getattr(interaction.user, "voice", None)
    if not user_voice or not user_voice.channel:
        await interaction.followup.send(
            "⚠️ **Bạn chưa tham gia Kênh thoại nào!**\n"
            "Vui lòng vào một Voice Channel trong Server trước rồi bấm lại nút nhé!",
            ephemeral=True
        )
        return

    voice_channel: discord.VoiceChannel = user_voice.channel
    guild = interaction.guild
    if not guild:
        await interaction.followup.send("⚠️ Tính năng Voice chỉ khả dụng trong Máy chủ (Server).", ephemeral=True)
        return

    # 2. Kiểm tra xung đột Voice trong cùng Server
    if guild.id in _active_voice_guilds:
        await interaction.followup.send(
            "⏳ **Bot đang bận đọc bài ở một kênh thoại khác trong Server!** Vui lòng chờ một lát nhé.",
            ephemeral=True
        )
        return

    style_info = READER_STYLES.get(reader_style, READER_STYLES["neutral"])
    reader_name = style_info.get("name", "Reader")

    # Thông báo bắt đầu kết nối
    await interaction.followup.send(
        f"🎙️ **{reader_name}** đang chuẩn bị giọng đọc và kết nối vào kênh **🔊 {voice_channel.name}**...",
        ephemeral=True
    )

    _active_voice_guilds.add(guild.id)
    voice_client: Optional[discord.VoiceClient] = None
    temp_audio_path: Optional[str] = None

    try:
        # 3. Sinh file âm thanh từ Gemini 2.5 Audio TRƯỚC khi join vào voice channel
        temp_audio_path = await generate_tarot_speech(
            reading_text=reading_text,
            reader_style=reader_style,
            user_name=interaction.user.display_name,
            spread_name=spread_name
        )

        if not temp_audio_path or not os.path.exists(temp_audio_path):
            await interaction.followup.send(
                f"🌌 **{reader_name} không thể truyền tải giọng đọc lúc này** do tín hiệu âm thanh bị gián đoạn. Bạn hãy thử lại sau nhé!",
                ephemeral=True
            )
            return

        # 4. Kiểm tra và dọn dẹp các session voice cũ (nếu có) trước khi kết nối
        existing_vc = guild.voice_client
        if existing_vc:
            if existing_vc.is_connected():
                if existing_vc.channel.id != voice_channel.id:
                    await existing_vc.move_to(voice_channel)
                voice_client = existing_vc
            else:
                try:
                    await existing_vc.disconnect(force=True)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                voice_client = await voice_channel.connect(timeout=15.0, reconnect=False, self_deaf=True)
        else:
            voice_client = await voice_channel.connect(timeout=15.0, reconnect=False, self_deaf=True)

        # 5. Phát âm thanh qua FFmpeg
        finished_event = asyncio.Event()

        def _after_play(error):
            if error:
                print(f"⚠️ [Tarot Voice] Lỗi khi phát audio: {error}", flush=True)
            finished_event.set()

        # Dùng FFmpegPCMAudio
        audio_source = discord.FFmpegPCMAudio(temp_audio_path)
        voice_client.play(audio_source, after=_after_play)
        print(f"🔊 [Tarot Voice] Đang phát bài đọc của {reader_name} trong kênh '{voice_channel.name}'...", flush=True)

        # 6. Chờ phát xong hoặc kiểm tra nếu phòng trống
        while not finished_event.is_set():
            if not voice_client.is_connected():
                break
            # Kiểm tra nếu chỉ còn bot trong phòng (trừ các bot khác)
            human_members = [m for m in voice_channel.members if not m.bot]
            if not human_members:
                print(f"🏃 [Tarot Voice] Kênh '{voice_channel.name}' không còn ai nghe, dừng phát...", flush=True)
                if voice_client.is_playing():
                    voice_client.stop()
                break
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"❌ [Tarot Voice] Lỗi trong quá trình phát Voice: {e}", flush=True)
        try:
            await interaction.followup.send(
                f"⚠️ Đã có sự cố xảy ra khi kết nối kênh thoại: `{e}`",
                ephemeral=True
            )
        except Exception:
            pass

    finally:
        # 7. Dọn dẹp tài nguyên và ngắt kết nối
        _active_voice_guilds.discard(guild.id)
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.disconnect(force=True)
                print(f"👋 [Tarot Voice] Đã rời kênh thoại '{voice_channel.name}'.", flush=True)
            except Exception as dc_err:
                print(f"⚠️ [Tarot Voice] Lỗi khi ngắt kết nối voice: {dc_err}", flush=True)

        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.remove(temp_audio_path)
                print(f"🧹 [Tarot Voice] Đã xóa file tạm: {temp_audio_path}", flush=True)
            except Exception as del_err:
                print(f"⚠️ [Tarot Voice] Lỗi xóa file tạm: {del_err}", flush=True)
