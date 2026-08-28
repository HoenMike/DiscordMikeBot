# Changelog

All notable changes to the **MikeDaBot** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`Major.Minor.BugFix`).

---

## [2.0.1] - 2026-08-28

### Added
- **Threads Embed Enhancements**: Hỗ trợ đầy đủ các định dạng URL Threads (`@user/post/ID`, `threads.net/t/ID`, `threads.net/share/post/ID`, `threads.net/share/ID`).
- **vxthreads.com Integration**: Bổ sung proxy chính `vxthreads.com` với OpenGraph parser tốc độ cao kèm fallback `fixthreads.seria.moe`.
- **Centralized Constants (`core/constants.py`)**: Gom nhóm toàn bộ cấu hình AI Models (`gemini-3.7-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`), nhiệt độ generation, processing limits và proxy definitions vào `core/constants.py`.

### Changed
- **Architectural Cleanup**: Loại bỏ hoàn toàn phụ thuộc ngược từ `core/config_manager.py` vào `features/embed/constants.py`.
- **Presence UI Cleanup**: Loại bỏ emoji bóng tròn màu sắc khỏi dòng trạng thái bot và Web Dashboard, hiển thị tối giản và thanh lịch.

---

## [2.0.0] - 2026-08-28 — *Hybrid Engine & Dynamic Presence*

### Added
- **Auto-Embed 9 Nền Tảng MXH**: Facebook, TikTok, Instagram, Twitter/X, Reddit, Threads, Pixiv, Bluesky, Twitch.
- **Suppress Mode & Subtext Jump Link**: Bảo toàn 100% tin nhắn và ảnh gốc, dòng chú thích `-# ↩️ [Trả lời Tên](link) • 🔗 [Xem bài viết](url)`.
- **Auto-Delete Synchronization**: Tự động xóa Embed khi người dùng xóa tin nhắn gốc chứa link.
- **Force Spoiler & Smart NSFW**: Tự động che mờ khi bọc trong `||link||` hoặc có từ khóa nhạy cảm.
- **Tarot AI Deep Reasoning 2.0**: 9 kiểu trải bài, 3 Reader AI (Orion, Celeste, Jester), Canvas rendering 78 lá bài Rider-Waite, Modal hỏi thêm AI và Community Rating 👍/👎.
- **AI Summary 2.0**: Quét sâu tới 2500 tin nhắn bằng Gemini Flash AI, timeline chi tiết, action items và gửi kết quả qua DM.
- **Web Admin Dashboard**: Live Console Streaming, Live Activity Logger, Điều khiển Dynamic Presence.
- **Cloud Database (Turso LibSQL)**: Tự động kết nối Turso LibSQL Cloud kết hợp Local SQLite fallback và Auto-Pruning.

---

## [1.2.5] - 2026-08-27

### Added
- **Turso LibSQL Cloud Integration**: Lưu trữ bền vững `bot_activities` và `console_logs` lên cloud.
- **Guild Suspension System**: Tạm ngừng/mở lại quyền sử dụng bot kèm lý do và in-memory cache.
- **Tarot Metadata**: Bổ sung mood tags, summary headlines và xuất dữ liệu đánh giá quẻ bài.

---

## [1.2.0] - 2026-08-25

### Added
- **Tarot Engine 78 Lá**: Bộ bài 78 lá Rider-Waite, Canvas Pillow renderer, 3 Reader personas.
- **Multi-Tier Embed Pipeline**: Pipeline URL tự động (API Fetcher ➔ Proxy Chain ➔ yt-dlp).
- **Modular Cog Architecture**: Tái cấu trúc sang `features/tarot`, `features/embed`, `features/summary`.
- **Hybrid Commands**: Hỗ trợ đồng thời Slash Command (`/`) và Prefix (`$m`).

---

## [1.1.0] - 2026-08-04

### Added
- **Auto-Embed Cơ Bản**: Tự động nhận diện liên kết MXH và bộ lọc NSFW sơ bộ.
- **Gemini Flash Lite**: Chuyển đổi mô hình AI sang Gemini Flash Lite tăng tốc độ phản hồi.

---

## [1.0.0] - 2026-06-13

### Added
- **Khởi Tạo Dự Án MikeDaBot**: Chạy song song Discord Bot Gateway và Flask Web Server trên Render.
- **MapReduce Summary Engine**: Tóm tắt song song tới 2500 tin nhắn với Google Gemini AI.
- **AI Self-Audit**: Lệnh `/test_tomtat` và báo cáo kiểm thử tự động.
- **Gunicorn Single-Worker Threading**: Thread safety cho Discord Gateway chống lỗi 502 Bad Gateway.
