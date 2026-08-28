# Changelog

All notable changes to the **MikeDaBot** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`Major.Minor.BugFix`).

---

## [2.4.4] - 2026-08-28 — *DND Status Policy & Presence Refinement*

### Changed
- **DND Error Policy**: Quy định trạng thái bot khi gặp sự cố hoặc bảo trì luôn được chuyển sang chế độ Do Not Disturb (DND - Chấm đỏ) thay vì Offline để đảm bảo người dùng luôn đọc được lý do và tiến độ xử lý trực tiếp trên Discord.
- **Set Error Handler**: Bổ sung hàm `presence_manager.set_error()` kích hoạt DND và cập nhật lý do lỗi tự động.

---

## [2.4.3] - 2026-08-28 — *Thread Safety & Config Import Fix*

### Fixed
- **Config Import in app.py**: Bổ sung `import config` vào `app.py` phục vụ tiến trình khởi chạy `bot.run(config.DISCORD_TOKEN)`.
- **Thread-Safe Logging Reentrancy**: Sử dụng `threading.RLock()` và cờ reentrancy guard cho `LogStreamRedirector` trong `config.py` chống lỗi `RuntimeError: reentrant call inside BufferedWriter` trên Python 3.14 Render.

---

## [2.4.2] - 2026-08-28 — *WSGI Stability & Flask Imports*

### Fixed
- **Flask Imports**: Bổ sung đầy đủ các dependency của Flask (`render_template`, `request`, `jsonify`, `redirect`, `url_for`, `session`, `Response`) vào `web/app.py`, khắc phục lỗi `NameError: name 'Flask' is not defined` trên Gunicorn Render.
- **Eager Bot Startup**: Đảm bảo Discord Bot worker thread tự động khởi chạy an toàn khi Gunicorn nạp module.

---

## [2.4.1] - 2026-08-28 — *Threads Enhancement & Centralized Constants*

### Added
- **Threads Embed Enhancements**: Hỗ trợ đầy đủ các định dạng URL Threads (`@user/post/ID`, `threads.net/t/ID`, `threads.net/share/post/ID`, `threads.net/share/ID`, và ID có chứa ký tự gạch ngang/gạch dưới).
- **vxthreads.com Integration**: Bổ sung proxy chính `vxthreads.com` với OpenGraph parser tốc độ cao kèm fallback `fixthreads.seria.moe`. Tự động chuẩn hóa đường dẫn `/share/` sang `/t/`.
- **Centralized Constants (`core/constants.py`)**: Gom nhóm toàn bộ cấu hình AI Models (`gemini-3.7-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`), nhiệt độ generation, processing limits và proxy definitions vào `core/constants.py`.

### Fixed
- **Presence Payload Fix**: Sửa lỗi không hiển thị Custom Status do thiếu trường `state` trong payload của Discord Gateway.
- **Eager Bot Startup**: Tự động kích hoạt bot worker thread ngay khi Gunicorn nạp module (không cần đợi request đầu tiên).
- **Presence UI Cleanup**: Làm sạch status text sang `Live v2.4.1 | $m help` và loại bỏ emoji bóng tròn màu sắc.

### Changed
- **Architectural Cleanup**: Loại bỏ hoàn toàn phụ thuộc ngược từ `core/config_manager.py` vào `features/embed/constants.py`.

---

## [2.4.0] - 2026-08-28 — *Auto-Embed QoL & Dynamic Presence*

### Added
- **Auto-Embed 9 Nền Tảng MXH**: Facebook, TikTok, Instagram, Twitter/X, Reddit, Threads, Pixiv, Bluesky, Twitch.
- **Suppress Mode & Subtext Jump Link**: Bảo toàn 100% tin nhắn và ảnh gốc, dòng chú thích siêu nhỏ `-# ↩️ [Trả lời Tên](link) • 🔗 [Xem bài viết](url)`.
- **Auto-Delete Synchronization**: Tự động xóa Embed khi người dùng xóa tin nhắn gốc chứa link.
- **Force Spoiler & Smart NSFW**: Tự động che mờ khi bọc trong `||link||` hoặc có từ khóa nhạy cảm (`nsfw`, `18+`, `spoiler`, `nhạy cảm`...).
- **Web Admin Dashboard & Database**: Live Console Streaming, Live Activity Logger, Điều khiển Dynamic Presence qua Web & Discord.
- **Database Auto-Pruning**: Tự động dọn dẹp `console_logs` (2000), `bot_activities` (5000), `tarot_history` (90 ngày).

---

## [2.3.1] - 2026-08-28 — *Tarot AI Refinements & Community Rating*

### Added
- **Community Rating**: Nút đánh giá quẻ bài Tarot (👍/👎) lưu trữ trực tiếp vào cơ sở dữ liệu.
- **Follow-up AI Question Modal**: Modal tương tác cho phép người dùng hỏi thêm ý nghĩa chi tiết sau khi bốc bài.
- **Markdown Response Parsing**: Tái cấu trúc parser markdown tự động trích xuất Topic, Mood, Summary headline và Content từ AI.

---

## [2.3.0] - 2026-08-27 — *Turso Cloud DB & Guild Management*

### Added
- **Turso LibSQL Cloud Database**: Tích hợp Cloud SQLite qua async client và quản lý vòng đời kết nối an toàn.
- **Activity & Log Persistence**: Lưu trữ bền vững `bot_activities` và `console_logs` vào Cloud DB.
- **Guild Suspension System**: Tạm ngừng / mở lại quyền sử dụng bot cho từng Server kèm lý do và In-memory Cache (0ms latency).
- **Web Console Security**: Xác thực đăng nhập bằng HMAC SHA-256 chống timing attack.
- **Tarot Metadata**: Bổ sung Mood Tags, Summary Headlines và API xuất dữ liệu đánh giá (`/api/tarot/ratings/export`).

---

## [2.2.0] - 2026-08-25 — *Summary Scan Enhancements & Error Logging*

### Added
- **Advanced Summary Filtering**: Lọc tin nhắn theo ngày cụ thể, khung giờ bắt đầu - kết thúc và message anchor link.
- **DM Delivery**: Tùy chọn gửi kết quả tóm tắt trực tiếp qua tin nhắn riêng (DM).
- **Expanded Scan Limit**: Mở rộng giới hạn quét tin nhắn lên tới 2500 tin với tùy chỉnh kích thước chunk MapReduce.
- **Dashboard Log Filtering**: Phân loại và lọc error logs theo cấp độ trên Web Dashboard.

---

## [2.1.0] - 2026-08-25 — *Tarot Launcher UX & Modular Refinements*

### Added
- **Hybrid Command System**: Hỗ trợ đồng thời Slash Command (`/`) và Prefix (`$m`).
- **HelpView UI**: Giao diện trợ giúp phân loại theo từng tính năng kèm nút đóng tin nhắn.
- **Cosmic Energy Seed**: Cơ chế hạt nhân năng lượng theo khung giờ (1h) đảm bảo tính nhất quán tâm linh.

### Changed
- **Architectural Streamlining**: Tinh giản các module thử nghiệm phụ (TTS Voice, Meme Search) để tối đa hóa hiệu năng cho AI Reasoning và Canvas Rendering.

---

## [2.0.0] - 2026-08-24 — *Modular Cogs Architecture, Tarot 78 Lá & Multi-Tier Embed*

### Added
- **Tarot Engine 78 Lá**: Bộ bài 78 lá Rider-Waite hoàn chỉnh, Canvas Pillow renderer độ nét cao, 3 phong cách Reader AI (Orion, Celeste, Jester).
- **Interactive Card Flip**: Giao diện lật từng lá bài tương tác với hiệu ứng mặt sau.
- **Multi-Tier Embed Pipeline**: Pipeline URL tự động (API Fetcher ➔ Proxy Chain ➔ yt-dlp fallback) kèm Cooldown Cache cho proxy lỗi.
- **Modular Cog Architecture**: Tái cấu trúc sang `features/tarot`, `features/embed`, `features/summary`.
- **Web Admin Dashboard**: Ra mắt phiên bản đầu tiên của Web Admin Dashboard.

---

## [1.1.0] - 2026-08-04 — *Auto-Embed MXH Cơ Bản & Gemini Flash Lite*

### Added
- **Auto-Embed Cơ Bản**: Tự động nhận diện liên kết Facebook, TikTok, Instagram và nhúng video tự động.
- **NSFW Keyword Filter**: Bộ lọc từ khóa nội dung nhạy cảm sơ bộ.
- **Gemini Flash Lite**: Chuyển đổi mô hình AI sang `gemini-3.5-flash-lite` và `gemini-3.6-flash` giúp tăng tốc độ phản hồi.

---

## [1.0.0] - 2026-06-13 — *Khởi Tạo Dự Án MikeDaBot*

### Added
- **Nền Tảng Hybrid Engine**: Chạy song song Discord Bot Gateway và Flask Web Server phục vụ triển khai Render.
- **MapReduce Summary Engine**: Tóm tắt song song tới 2500 tin nhắn bằng Google Gemini AI với Anti-hallucination guardrails (Temperature=0.1).
- **AI Self-Audit**: Lệnh kiểm thử `/test_tomtat` và báo cáo kiểm thử tự động trên Dashboard.
- **Gunicorn Thread Safety**: Thiết lập Gunicorn Single-Worker Threading giải quyết lỗi 502 Bad Gateway.
