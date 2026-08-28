"""
core/version.py - Quản lý phiên bản (Semantic Versioning) và Nhật ký phát hành (Patchnotes / Changelog).

Quy tắc phiên bản: Major.Minor.BugFix (Ví dụ: 2.0.0)
- Major: Đại tu kiến trúc hoặc thay đổi nền tảng lớn (1.x.x -> 2.x.x)
- Minor: Bổ sung tính năng mới hoặc nâng cấp module lớn (2.0.0 -> 2.1.0)
- BugFix: Sửa lỗi / Hotfix / Tinh chỉnh cho phiên bản hiện tại (2.0.0 -> 2.0.1)
"""

from typing import Dict, List, Any, Optional
import discord

CURRENT_VERSION = "2.0.0"
RELEASE_DATE = "2026-08-28"
CODENAME = "Hybrid Engine & Dynamic Presence"

# Lịch sử các phiên bản phát hành (Mới nhất nằm ở đầu)
CHANGELOG: List[Dict[str, Any]] = [
    {
        "version": "2.0.0",
        "date": "2026-08-28",
        "type": "major",  # 'major' | 'minor' | 'bugfix'
        "title": "Đại Tu Kiến Trúc Hybrid Engine & Nâng Cấp Toàn Diện",
        "summary": "Phiên bản nâng cấp lớn 2.0 với hệ thống Auto-Embed 9 MXH tinh gọn, Tarot AI đa tầng, AI Summary 2500 tin, Web Dashboard Real-time & Dynamic Presence.",
        "changes": [
            {
                "category": "👑 Auto-Embed 9 Nền Tảng",
                "items": [
                    "Bổ sung hỗ trợ đầy đủ 9 mạng xã hội: Facebook, TikTok, Instagram, Twitter/X, Reddit, Threads, Pixiv, Bluesky, Twitch.",
                    "Cơ chế Suppress Embed gốc: Giữ nguyên 100% tin nhắn & tệp đính kèm, bảo toàn tính năng highlight vàng khi reply.",
                    "Subtext Jump Link: Dòng chú thích siêu nhỏ `-# ↩️ [Trả lời Tên](link) • 🔗 [Xem bài viết](url)`, nhấp vào cuộn ngay về tin gốc mà không bị lặp chữ.",
                    "Tự động xóa Embed đồng bộ khi người dùng xóa tin nhắn gốc chứa link.",
                    "Force Spoiler & Tự động nhận diện từ khóa nhạy cảm (nsfw, 18+, spoiler, nhạy cảm...) để che mờ khung embed."
                ]
            },
            {
                "category": "🔮 Tarot AI Deep Reasoning 2.0",
                "items": [
                    "9 kiểu trải bài chuyên sâu từ 1 lá đến 10 lá Celtic Cross.",
                    "3 AI Reader tính cách độc đáo (Orion, Celeste, Jester) + Chế độ ngẫu nhiên.",
                    "Canvas Renderer kết xuất hình ảnh 78 lá Rider-Waite độ phân giải cao.",
                    "Cơ chế Cosmic Energy Seed (1h) đảm bảo tính nhất quán tâm linh.",
                    "Nút tương tác sau quẻ bài: Hỏi Thêm Ý Nghĩa (Modal AI) & Nút Đánh Giá (👍/👎)."
                ]
            },
            {
                "category": "📝 Tóm Tắt Tin Nhắn AI 2.0",
                "items": [
                    "Sử dụng Gemini Flash AI quét sâu tới 2500 tin nhắn với tốc độ cao.",
                    "Tự động lọc spam/lệnh bot, trích xuất Action Items (kèm người phụ trách) & Top thành viên tích cực.",
                    "Hỗ trợ quét theo số giờ, ngày cụ thể, khung giờ hoặc message anchor."
                ]
            },
            {
                "category": "🌐 Web Dashboard & Cloud Database",
                "items": [
                    "Trang Quản trị Web trực quan với Live Console Streaming & Live Activity Logger.",
                    "Unified Database Adapter: Tự động kết nối Turso LibSQL Cloud và fallback an toàn sang Local SQLite.",
                    "Cơ chế Auto-Pruning tự động dọn dẹp log cũ, chống tràn và tiết kiệm 95% quota ghi DB.",
                    "Hệ thống Dynamic Presence & Status: Cập nhật trạng thái bot linh hoạt qua Web & Discord."
                ]
            }
        ]
    },
    {
        "version": "1.2.0",
        "date": "2026-08-15",
        "type": "minor",
        "title": "Nâng Cấp Hệ Thống Tarot AI & Canvas Rendering",
        "summary": "Tích hợp công nghệ ghép ảnh trải bài trực quan và đa dạng hóa tính cách Reader.",
        "changes": [
            {
                "category": "🔮 Tarot Engine",
                "items": [
                    "Tích hợp thư viện Pillow render hình ảnh trải bài Canvas 78 lá Rider-Waite.",
                    "Bổ sung 3 Reader AI với giọng văn riêng biệt (Orion, Celeste, Jester).",
                    "Thêm tính năng lật từng lá bài tương tác trực tiếp trên Discord."
                ]
            }
        ]
    },
    {
        "version": "1.1.0",
        "date": "2026-08-01",
        "type": "minor",
        "title": "Tích Hợp Tóm Tắt Kênh Chat AI (Gemini Flash)",
        "summary": "Ra mắt tính năng tóm tắt thông minh cuộc trò chuyện cho Discord server.",
        "changes": [
            {
                "category": "📝 Summary Engine",
                "items": [
                    "Tích hợp Google Gemini AI đọc và đúc kết nội dung tin nhắn.",
                    "Hỗ trợ phân loại chủ đề và xuất ra định dạng ngắn gọn / chi tiết."
                ]
            }
        ]
    },
    {
        "version": "1.0.0",
        "date": "2026-07-20",
        "type": "major",
        "title": "Khởi Tạo Dự Án MikeDaBot",
        "summary": "Khởi tạo nền móng đầu tiên cho bot Discord đa nhiệm và hệ thống quản trị Web.",
        "changes": [
            {
                "category": "🚀 Khởi Tạo",
                "items": [
                    "Xây dựng kiến trúc Hybrid (Discord bot + Flask Web Server chạy song song).",
                    "Thiết lập hệ thống lệnh Prefix `$m` cơ bản và kết nối Discord Gateway."
                ]
            }
        ]
    }
]


def get_version_info() -> Dict[str, Any]:
    """Trả về thông tin chi tiết về phiên bản hiện tại."""
    return {
        "version": CURRENT_VERSION,
        "release_date": RELEASE_DATE,
        "codename": CODENAME,
        "total_releases": len(CHANGELOG),
        "latest_patchnote": CHANGELOG[0] if CHANGELOG else None
    }


def get_changelog() -> List[Dict[str, Any]]:
    """Trả về toàn bộ danh sách các bản cập nhật."""
    return CHANGELOG


def build_version_embed(user: Optional[discord.User | discord.Member] = None) -> discord.Embed:
    """Xây dựng Discord Embed hiển thị thông tin phiên bản và patchnote mới nhất."""
    latest = CHANGELOG[0]
    
    badge_type = {
        "major": "🚀 [MAJOR RELEASE]",
        "minor": "✨ [FEATURE UPDATE]",
        "bugfix": "🛠️ [BUG FIX / HOTFIX]"
    }.get(latest.get("type", "minor"), "✨ [UPDATE]")

    embed = discord.Embed(
        title=f"🤖 THÔNG TIN PHIÊN BẢN MIKEBOT — v{CURRENT_VERSION}",
        description=(
            f"**{badge_type}**: **{latest['title']}**\n"
            f"📅 **Ngày phát hành:** `{latest['date']}` • **Codename:** *{CODENAME}*\n\n"
            f"*{latest['summary']}*"
        ),
        color=0x7851A9
    )

    for cat in latest.get("changes", []):
        items_text = "\n".join(f"• {item}" for item in cat["items"])
        embed.add_field(
            name=cat["category"],
            value=items_text,
            inline=False
        )

    embed.add_field(
        name="📜 Lịch Sử Các Phiên Bản Trước",
        value="\n".join(
            f"• `v{rel['version']}` ({rel['date']}): **{rel['title']}**"
            for rel in CHANGELOG[1:]
        ) or "*(Không có phiên bản cũ hơn)*",
        inline=False
    )

    if user:
        embed.set_footer(
            text=f"Yêu cầu bởi {user.display_name} • MikeDaBot Version Tracker",
            icon_url=user.display_avatar.url if user.display_avatar else None
        )
    return embed
