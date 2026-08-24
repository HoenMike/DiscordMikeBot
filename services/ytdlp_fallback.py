import asyncio
from services.platform_fetchers import PostData

# Cấu hình yt-dlp: chỉ trích xuất thông tin, không tải file
_YTDLP_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,
    "no_color": True,
    "socket_timeout": 15,
    "format": "best[ext=mp4]/best",
    "noplaylist": True,
}

# Thời gian chờ tối đa cho toàn bộ tiến trình yt-dlp (giây)
_YTDLP_TIMEOUT = 30


def _extract_sync(url: str) -> dict | None:
    """Đồng bộ: chạy yt-dlp để trích xuất thông tin media.

    Hàm này được gọi trong thread riêng qua asyncio.to_thread().
    """
    try:
        import yt_dlp
    except ImportError:
        print(
            "[yt-dlp] Thư viện yt-dlp chưa được cài đặt. "
            "Chạy 'pip install yt-dlp' để sử dụng fallback này.",
            flush=True,
        )
        return None

    try:
        with yt_dlp.YoutubeDL(_YTDLP_OPTS) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            return info
    except Exception as e:
        print(
            f"[yt-dlp] Lỗi khi trích xuất dữ liệu từ {url}: {e}",
            flush=True,
        )
        return None


async def extract_media_ytdlp(url: str, platform_key: str) -> PostData | None:
    """Trích xuất media URL trực tiếp bằng yt-dlp (fallback cuối cùng).

    Chạy trong thread riêng để không chặn event loop.
    Bọc trong asyncio.wait_for() với timeout cố định để tránh treo vĩnh viễn.
    Trả về PostData nếu thành công, None nếu thất bại hoặc hết thời gian.
    """
    print(
        f"[yt-dlp] Bắt đầu trích xuất từ {url} (nền tảng: {platform_key})",
        flush=True,
    )

    try:
        info = await asyncio.wait_for(
            asyncio.to_thread(_extract_sync, url),
            timeout=_YTDLP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        print(
            f"[yt-dlp] Hết thời gian chờ ({_YTDLP_TIMEOUT}s) khi xử lý {url}",
            flush=True,
        )
        return None
    except Exception as e:
        print(
            f"[yt-dlp] Lỗi thread khi xử lý {url}: {e}",
            flush=True,
        )
        return None

    if not info:
        print(
            f"[yt-dlp] Không trích xuất được dữ liệu từ {url}",
            flush=True,
        )
        return None

    # Xác định URL media trực tiếp và thumbnail
    media_url = info.get("url")
    thumbnail = info.get("thumbnail")

    # Tìm thumbnail có độ phân giải cao nhất
    thumbnails = info.get("thumbnails", [])
    best_thumb = thumbnail
    if thumbnails:
        thumb_obj = max(
            thumbnails,
            key=lambda t: (t.get("height", 0) or 0) * (t.get("width", 0) or 0),
            default=None,
        )
        if thumb_obj and thumb_obj.get("url"):
            best_thumb = thumb_obj["url"]

    media_urls = []
    media_type = "text"

    # Ưu tiên video URL trực tiếp
    if media_url:
        media_urls.append(media_url)
        media_type = "video"
    elif best_thumb:
        media_urls.append(best_thumb)
        media_type = "image"

    title = info.get("title", "")
    uploader = info.get("uploader") or info.get("channel") or "Unknown"
    uploader_url = info.get("uploader_url") or info.get("channel_url")

    post_data = PostData(
        platform=platform_key,
        author=uploader,
        author_url=uploader_url,
        author_avatar=None,
        text=title if title else None,
        media_urls=media_urls,
        media_type=media_type,
        is_nsfw=info.get("age_limit", 0) >= 18,
        likes=info.get("like_count"),
        comments=info.get("comment_count"),
        retweets=None,
        url=info.get("webpage_url", url),
        timestamp=info.get("upload_date"),
        thumbnail_url=best_thumb,
    )

    print(
        f"[yt-dlp] Trích xuất thành công từ {url}: "
        f"media_type={media_type}, số media={len(media_urls)}",
        flush=True,
    )

    return post_data
