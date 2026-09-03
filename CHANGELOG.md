# Changelog

All notable changes to the **MikeDaBot** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`Major.Minor.BugFix`).

---

## [2.4.12] - 2026-09-03 — *Canonical Facebook Watch Proxy Format & Clean Embed Layout*

### Changed
- **Chuẩn Hóa Đường Dẫn Facebook watch?v= (Chuẩn RePlay)**: Tự động chuyển đổi các đường dẫn Facebook Reels (`/reel/ID`), Videos (`/videos/ID`) và Watch sang `https://facebed.com/watch?v=ID` để Facebed và Discord xử lý bung video player tối ưu nhất.
- **Dỡ bỏ kiểm tra has_image quá nghiêm ngặt**: Cho phép `facebed.com` hoạt động bình thường, không bị đánh trượt nhầm sang yt-dlp khi proxy vẫn hoạt động tốt trên Discord.
- **Tinh gọn giao diện Embed**: Tự động ẩn ảnh thumbnail tĩnh trong embed khi file video MP4 đã được đính kèm, loại bỏ hoàn toàn tình trạng lặp 2 lần hình ảnh trong cùng một tin nhắn.

---

## [2.4.11] - 2026-09-03 — *Multi-candidate Video Downloader & Proxy Fallback Hint*

### Added
- **Trình Phát Video Native & Tự Động Thử Định Dạng (Multi-Candidate)**: Hệ thống tự động quét tất cả các định dạng video MP4 (progressive HD/SD) từ `yt-dlp`. Nếu định dạng HD vượt quá giới hạn tải lên của Discord (> 25MB), hệ thống tự động thử định dạng tiếp theo (như SD 7.74MB $\le$ 25MB) để đảm bảo luôn đính kèm được video phát trực tiếp có âm thanh, không bị rơi về ảnh tĩnh.
- **Thông Báo Fallback Trực Quan**: Khi xảy ra fallback do Facebed/Proxy gặp sự cố, bot tự động đính kèm thông báo rõ ràng trên header: `⚠️ Facebed lỗi, đã tự động fallback` và footer embed `Facebook • Fallback từ facebed`.

---

## [2.4.10] - 2026-09-03 — *Active Discord Unfurl Verification & Facebook yt-dlp & Lifecycle Presence*

### Added
- **Cơ Chế Giám Sát Unfurl Discord (Active Unfurl Verification)**: Tự động bắt sự kiện `message_edit` từ Discord Gateway sau khi gửi proxy URL. Nếu sau 2.5s Discord âm thầm hủy embed (do lỗi CDN 403 hoặc thiếu thẻ OpenGraph), bot tự động xóa tin nhắn rỗng và kích hoạt Fallback Tier 2 (yt-dlp) ngay lập tức, ngăn ngừa hoàn toàn tình trạng để lại link trống trong chat.
- **Tích hợp yt-dlp trực tiếp vào Facebook (Tier 0)**: Trích xuất trực tiếp bài viết/reels Facebook qua `yt-dlp` chỉ trong ~3.5s với đầy đủ Tiêu đề, Tác giả, Thumbnail gốc Facebook (không bao giờ bị 403) và tải đính kèm file video MP4 (<= 25MB) để Discord phát native có tiếng.
- **Hệ thống Watchdog & Trạng Thái Vòng Đời Bot (Lifecycle Presence)**:
  - Loại bỏ các lệnh slash xoay tua rườm rà, cố định trạng thái: `Live v2.4.10 | .m help`.
  - Tự động chuyển sang `Updating...` (Cam 🟡) trước khi tắt tiến trình trên Render/Gunicorn.
  - Tự động nhảy sang `Error` (Đỏ 🔴 / DND) khi độ trễ Gateway > 5.0s hoặc mất kết nối, và tự động hồi phục Xanh 🟢 khi bình thường.

### Fixed
- **Chuẩn hóa đường dẫn Facebook**: Tự động chuyển đổi `/share/v/` sang `/share/r/` để tăng độ tương thích với các bộ giải mã mạng xã hội.
- **Bộ lọc Proxy khuyết tật**: Cập nhật `validator.py` bắt buộc phải có ảnh poster (`og:image`) đối với video proxy Facebook, loại bỏ các proxy chỉ có `og:video` trỏ về CDN bị chặn như `facebed.com`.

---

## [2.4.9] - 2026-09-03 — *TikTok Embed Stream Fix & Domain Cache Hardening*

### Fixed
- **Khắc phục lỗi "Image failed to load" trên TikTok**: Loại bỏ hoàn toàn proxy `tiktxk.com` (do Akamai 403 trên endpoint video của dự án đã bị bỏ hoang), chuyển sang ưu tiên `tnktok.com` (fxTikTok chính thức) và `tfxktok.com` để hiển thị video player native chuẩn xác 100%.
- **Thêm chữ ký nhận diện lỗi tiktxk**: Tự động bỏ qua các proxy sinh mã lỗi JSON `cannot read properties of undefined` hoặc giao diện `tiktxk`.
- **Bảo vệ Cache Cooldown Domain**: Chỉ đưa domain vào thời gian nghỉ cooldown khi gặp lỗi kết nối mạng thực sự (`ClientConnectorError`, DNS) hoặc mã máy chủ 502/503, tránh ngộ độc cache khi timeout trên một bài viết đơn lẻ.

---

## [2.4.8] - 2026-09-03 — *Embed Link Polish & Smart Fallback Optimization*

### Changed
- **Subtext Jump Link Clean up**: Bọc toàn bộ link proxy vào dạng markdown `[Xem bài viết gốc](url)`, hoàn toàn loại bỏ việc để lộ raw link dài/xấu ra giao diện chat.
- **Loại bỏ Reply Icon**: Lược bỏ icon `↩️` trước chữ Trả lời, định dạng đồng bộ siêu gọn: `-# [Trả lời](jump_url) **Tên** • [Xem bài viết gốc](url)`.

### Fixed
- **Loại bỏ kiểm tra Video Stream CDN gây lỗi 403**: Gỡ bỏ request GET trực tiếp tới CDN video trong `validator.py` (nguyên nhân chính khiến Facebook Reels trả về 403 và bị fallback thừa sang yt-dlp).
- **Cập nhật danh sách Proxy Domains**: Loại bỏ proxy chết hoặc lỗi video 403 (`kktiktok.com`, `kkinstagram.com`, `tiktxk.com`), ưu tiên các proxy hoạt động nhanh và chuẩn OpenGraph (`tnktok.com` fxTikTok, `tfxktok.com`, `vxreddit.com`, `fixthreads.seria.moe`).
- **Sửa API fxtwitter.com**: Cập nhật kiểm tra API fxtwitter để không từ chối các tweet chỉ chứa văn bản, tránh fallback thừa sang các proxy khác.
- **Bảo vệ Cache Domain**: Ngăn chặn tình trạng đưa nhầm domain vào danh sách blacklist 30s khi chỉ gặp lỗi 404 hoặc bài viết riêng tư.
- **Tối ưu Fallback Tier 2 (yt-dlp)**: Chỉ fallback sang yt-dlp cho các nền tảng video, giảm timeout từ 30s xuống 15s để xử lý nhanh chóng.

---

## [2.4.7] - 2026-08-28 — *Gunicorn Worker Lifecycle & Port Binding Fix*

### Fixed
- **Gunicorn Post-Fork Bot Startup**: Chuyển tiến trình khởi chạy Discord Bot thread vào hook `post_fork` trong `gunicorn.conf.py`, đảm bảo Bot và Flask cùng nằm trong 1 Worker process memory và giải quyết triệt để vấn đề mất luồng Bot Gateway sau khi Master fork.
- **Gunicorn Signal Safety**: Gỡ bỏ việc đăng ký đè `signal.SIGTERM` / `signal.SIGINT` ở cấp độ module import trong `app.py`, ngăn chặn tình trạng Gunicorn Master bị thoát đột ngột (`sys.exit(0)`) làm đóng cổng HTTP và gây lỗi `No open HTTP ports detected on 0.0.0.0` trên Render.
- **Public Health Check Endpoints**: Thêm 2 route công khai `/healthz` và `/ping` trả về HTTP 200 nhanh chóng mà không cần session đăng nhập, hỗ trợ Render Port Scanner và các dịch vụ keep-alive ping.

---

## [2.4.6] - 2026-08-28 — *Dot Prefix Migration (.m)*

### Changed
- **Prefix Migration**: Chuyển đổi tiền tố lệnh mặc định từ `$m` sang `.m` (`.m`, `.M`) trên toàn bộ hệ thống xử lý tin nhắn, bộ định tuyến lệnh và Bot Mention.
- **Presence Status & Help Views**: Cập nhật chuỗi trạng thái hoạt động sang `Live v2.4.6 | .m help` và đồng bộ cú pháp các lệnh `.m tarot`, `.m tomtat`, `.m ver` trong toàn bộ menu tương tác Discord.

---

## [2.4.5] - 2026-08-28 — *Tarot Terminology Polish & Help Updates*

### Changed
- **Tarot Terminology Polish**: Chuẩn hóa thuật ngữ sang `Bốc bài Tarot chiêm tinh` (lược bỏ chữ AI) trong chuỗi xoay tua trạng thái Presence và menu trợ giúp Discord.
- **Help Embed Consistency**: Đồng bộ footer và tiêu đề menu Help với phiên bản hiện tại.

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
