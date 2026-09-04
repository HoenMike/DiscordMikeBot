# Changelog

All notable changes to the **MikeDaBot** project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`Major.Minor.BugFix`).

---

## [2.6.0] - 2026-09-04 — *Public Guest Landing Page & Role-Based Dashboard Architecture*

### Added
- **Trang Khách Công Khai (`/` - Public Guest Landing Page)**:
  - Cho phép người dùng truy cập trực tiếp trang chủ mà không yêu cầu đăng nhập.
  - Hiển thị các thông số hoạt động trực tiếp (Online/Offline, Độ trễ ms, Uptime liên tục, Số máy chủ, Tiền tố `.m` & `/slash`) tự động cập nhật mỗi 5 giây qua `/api/public/stats`.
  - Showcase chi tiết 4 nhóm tính năng cốt lõi: Auto-Embed 9 mạng xã hội, Bốc bài Tarot chiêm tinh 78 lá, Tóm tắt tin nhắn hội thoại AI MapReduce và Hạ tầng Cloud 24/7.
  - **Nhật Ký Cập Nhật (Public Changelog)**: Hiển thị nổi bật phiên bản hiện tại kèm phân loại tính năng và danh sách Accordion tương tác xem lại toàn bộ 28 bản cập nhật trước đó từ `v2.5.3` về đến `v1.0.0`.
- **Phân Quyền Tuyến Đường & Tách Biệt Vai Trò (Role-Based Routing)**:
  - Trang Quản trị chuyển sang `/admin` và được bảo vệ nghiêm ngặt bằng `@login_required`, tự động chuyển hướng `/login?next=/admin` nếu chưa đăng nhập.
  - Phân tách API an toàn: Mở công khai `/api/public/stats` và `/api/version`; giữ bảo mật tuyệt đối cho các API quản trị (`/api/stats`, `/api/activities`, `/api/guilds`, `/api/tarot/*`).
- **Nâng Cấp Giao Diện Bảng Quản Trị & Đăng Nhập**:
  - Bổ sung nút "Xem Trang Khách" trên Header của Admin Dashboard.
  - Đồng bộ số hiệu phiên bản động trên toàn bộ các badge.
  - Trang đăng nhập (`/login`) bổ sung nút quay về Trang Khách và hỗ trợ chuyển hướng thông minh qua tham số `next`.

---

## [2.5.3] - 2026-09-04 — *Embed Reaction Desync Guard & Multi-User Notification Re-trigger*

### Fixed
- **Chống Lỗi Desync Khi Gỡ Reaction Trên Embed (`on_raw_reaction_remove`)**:
  - Truy vấn trực tiếp trạng thái Embed Preview từ Discord API khi nhận sự kiện rút reaction.
  - Nếu trên Embed Preview vẫn còn $\ge 1$ người thả emote đó (`count > 0`), bot bảo toàn reaction trên tin nhắn gốc, không gỡ nhầm.
  - Chỉ gỡ reaction trên tin nhắn gốc khi tất cả người dùng trên Embed đã gỡ hết emote đó về 0.
- **Kích Hoạt Lại Thông Báo Khi Thả Trùng Emote (`on_raw_reaction_add`)**:
  - Khi có người thứ 2+ cùng thả một emote đã có trên Embed Preview, bot tự động gỡ reaction của mình trên tin nhắn gốc và thả lại ngay (sau $0.3\text{s}$) để Discord kích hoạt lại push notification và hiệu ứng nảy emote cho người gửi tin gốc.
- **Khóa Đồng Bộ Per-Message (`asyncio.Lock`)**:
  - Bổ sung `self._reaction_locks` theo từng tin nhắn gốc, đảm bảo các luồng thêm/gỡ reaction đồng thời được xử lý tuần tự, loại bỏ hoàn toàn rủi ro race condition.

---

## [2.5.2] - 2026-09-04 — *Tarot Mention Context & Entity Awareness & Grey-Zone Banter Flexibility*

### Added
- **Nhận Diện Thực Thể & Chuẩn Hóa Tag/Mention (`extract_question_mentions_context`)**:
  - Tự động nhận diện và phân giải Discord raw mentions `<@123...>` thành `@DisplayName` để Gemini AI hiểu mượt mà.
  - Phân biệt rõ ràng 3 thực thể độc lập: Người yêu cầu bốc bài (`user_name`), Chính Bot (`bot_name`), và Thành viên khác trong server (`@Member`).
- **Khối Bối Cảnh Đối Tượng Được Tag Trong AI Prompt**:
  - Chèn bảng phân tích đối tượng và vai trò vào khối `THÔNG TIN QUẺ BÀI`, thông báo cho Reader biết chính xác người hỏi đang hướng sự chú ý đến ai trong cộng đồng.
- **Nới Lỏng Quy Chuẩn Vùng Xám & Đùa Vui (Không Quá Strict)**:
  - Bổ sung ngoại lệ vào Nguyên tắc 4: Các câu hỏi trêu đùa, khen ngợi, hỏi vui về bạn bè trong server (ví dụ: *"@Mike có siêu cấp đẹp gái không?"*, *"@A dạo này có giàu không?"*) luôn được xem là hợp lệ (`is_valid: true`), không bị từ chối khắt khe.
  - Chỉ từ chối khi thực sự có hành vi soi mói đời tư độc hại, bới móc bí mật cá nhân nhạy cảm giữa các bên thứ ba.
- **Định Hướng Luận Giải Đúng Đối Tượng (Nguyên Tắc 7)**:
  - Bổ sung Nguyên tắc 7 vào Prompt: Hướng dẫn AI giải mã năng lượng lá bài về thần thái, vẻ đẹp, phong cách của người được tag mà không nhầm lẫn với Bot.
  - Đưa ra lời nhắn nhủ, đối đáp dí dỏm kết nối giữa người hỏi và người bạn được tag theo đúng Persona.
- **Tích Hợp Toàn Diện Mọi Luồng Trải Bài**:
  - Đồng bộ truyền context qua Slash/Prefix flow (`cog.py`), Interactive Launcher View, và Modal hỏi đáp đào sâu bổ sung (`tarot_view.py`).

---

## [2.5.1] - 2026-09-04 — *Tarot Direct Focus & Grounded Symbolism & Yes/No Sync*

### Changed
- **Trực Diện & Xử Lý Câu Hỏi Meta / Thử Tài Bot (Direct Focus)**:
  - Bổ sung Nguyên tắc 5 vào AI Prompt: Ngăn chặn hoàn toàn việc AI tự suy diễn các câu hỏi thành tâm sự tình yêu lứa đôi hay văn mẫu chữa lành sáo rỗng.
  - Xử lý chuyên biệt cho các câu hỏi thử tài hoặc hỏi về bot (như *"Bot có biết bói tarot không?"*): Reader tự tin khẳng định vai trò, giải mã lá bài rút được theo đúng bối cảnh thử tài và gợi ý người dùng đặt câu hỏi thực tế.
- **Biểu Tượng Bám Sát Thực Tế & Lời Khuyên Hành Động (Grounded Symbolism & Actionable Advice)**:
  - Bắt buộc gắn hình ảnh, chi tiết lá bài vào sự việc của câu hỏi thay vì trích dẫn định nghĩa lý thuyết chung chung.
  - Chuẩn hóa mục Advice thành các bước hành động cụ thể (Actionable Steps).
- **Đồng Bộ Tuyệt Đối Phán Quyết Yes / No (Yes/No Verdict Sync)**:
  - Truyền trực tiếp kết quả phán quyết chính thức (Badge & Mô tả) vào AI Prompt để bài giải luôn đồng thuận, chấm dứt hoàn toàn tình trạng mâu thuẫn "trên CÓ, dưới KHÔNG".
- **Tinh Chỉnh Persona Readers**: Cập nhật chỉ dẫn giữ đúng trọng tâm câu hỏi cho Orion, Celeste và Jester.

---

## [2.5.0] - 2026-09-04 — *Tarot Ethics Boundary & Third-Party Privacy Protection*

### Added
- **Quy Chuẩn Đạo Đức & Ranh Giới Trải Bài Tarot (Tarot Ethics Boundary)**:
  - Bổ sung quy tắc kiểm tra tính hợp lệ của câu hỏi: Cho phép hỏi về người khác nếu người hỏi là người trong cuộc cần lời khuyên cho bản thân, nhưng tuyệt đối từ chối bốc bài hỏi thay hoặc soi mói đời tư/tình cảm/bí mật của người thứ ba (như trường hợp A bốc bài hỏi chuyện của B và C).
  - Tự động phản hồi từ chối phù hợp với tính cách của 3 Persona: Orion (nghiêm nghị, chuẩn mực), Celeste (dịu dàng, thấu cảm), Jester (cà khịa tếu táo tính hóng drama).
  - Áp dụng quy tắc đạo đức tương tự cho tính năng hỏi đáp đào sâu bổ sung (Follow-up Questions).
- **Vô Hiệu Hóa Phán Quyết Yes / No Khi Câu Hỏi Vi Phạm**: Tự động chuyển đổi badge phán quyết Yes/No thành `🚫 KHÔNG HỢP LỆ (VI PHẠM NGUYÊN TẮC)` khi câu hỏi vi phạm đạo đức Tarot.
- **Cập Nhật Giao Diện & Lưu Ý Người Dùng**: Bổ sung hướng dẫn và placeholder trực quan trong Modal nhập câu hỏi và Launcher UI.

---

## [2.4.15] - 2026-09-03 — *Startup Embed Orphan Scan & Realtime Deletion Logging*

### Added
- **Quét Dọn Embed Mồ Côi Khi Khởi Động (Startup Orphan Scanner)**: Tự động rà soát lịch sử tin nhắn bot trên các kênh chat sau khi khởi động. Xóa sạch các embed mồ côi nếu tin nhắn gốc đã bị xóa mất từ trước (trong lúc bot tắt hoặc redeploy), đồng thời khôi phục bộ nhớ cache theo dõi cho các embed còn hoạt động.
- **Ghi Nhận Sự Kiện Xóa Vào Live Dashboard & Console**: Toàn bộ sự kiện hủy tác vụ in-flight, thu hồi bản xem trước, và xóa embed tự động đều được ghi nhận chi tiết vào ActivityLogger (Web Dashboard) và Console logs thời gian thực.

---

## [2.4.14] - 2026-09-03 — *In-Flight Message Deletion Cancellation & Zero Orphan Embeds*

### Fixed
- **Hủy tác vụ và chặn gửi embed khi tin nhắn gốc bị xóa sớm**: Giải quyết dứt điểm tình trạng race condition khi người dùng xóa tin nhắn gốc trong lúc bot đang tải video hoặc gọi API chưa kịp rep. Hệ thống lập tức hủy `Task`, ngừng việc tải/gửi embed preview và tuyệt đối không để lại embed mồ côi trên kênh chat.
- **Hỗ trợ xóa hàng loạt (Bulk Delete)**: Bổ sung `on_raw_bulk_message_delete` để tự động dọn sạch các embed xem trước khi kênh chat bị purge.

---

## [2.4.13] - 2026-09-03 — *Native Facebed Preservation & Zero False Fallback*

### Fixed
- **Bảo toàn Embed Facebed & Loại bỏ tự xóa tin nhắn sớm**: Gỡ bỏ hoàn toàn bộ đếm 2.5s tự xóa tin nhắn (nguyên nhân khiến bot xóa mất embed Facebed của người dùng ngay khi Discord vừa tải xong và nhảy fallback thừa).
- **Trải nghiệm Embed tự nhiên**: Giữ nguyên tin nhắn chứa link proxy để Discord tự nhiên crawl và hiển thị video player native chuẩn xác 100% giống như bot RePlay.

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
