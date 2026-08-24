# MikeDaBot - Discord Summary Bot

Bot Discord tích hợp AI (Gemini / Gemma 4) chuyên tóm tắt lịch sử trò chuyện và tự động nhúng nội dung mạng xã hội.

---

## Tính năng

### Tóm tắt cuộc trò chuyện bằng AI

Bot quét lịch sử tin nhắn trong kênh chat và sử dụng mô hình Gemma 4 để tạo bản tóm tắt.

- **Chế độ ngắn gọn (`short`)**: Liệt kê các chủ đề chính và quyết định quan trọng dưới dạng gạch đầu dòng. Giới hạn khoảng 1000 ký tự.
- **Chế độ chi tiết (`long`)**: Tạo bản tóm tắt đầy đủ kèm timeline diễn biến, phân chia theo ngày, gộp nhóm các tin nhắn liên tục thành các mốc thời gian.
- **Chế độ tập trung (Focus)**: Cho phép chỉ định một chủ đề hoặc từ khóa cụ thể để bot phân tích sâu, bỏ qua các nội dung không liên quan.
- **MapReduce**: Khi số lượng tin nhắn vượt quá 300, bot tự động chia nhỏ dữ liệu, phân tích song song từng phần, sau đó tổng hợp lại thành một bản tóm tắt thống nhất.
- **Kiểm thử tự động**: Lệnh `/test_tomtat` chạy tóm tắt và gửi kết quả cho AI QA chấm điểm chất lượng. Kết quả được lưu trên Web Dashboard.

### Nhúng nội dung mạng xã hội (Social Media Embeds)

Bot tự động phát hiện các URL mạng xã hội trong tin nhắn và tạo embed tùy chỉnh thay thế embed mặc định của Discord. Người dùng chỉ cần dán link, không cần sử dụng lệnh.

**Các nền tảng được hỗ trợ:**

| Nền tảng       | Cơ chế chính (Tier 0 API)      | Fallback Proxies (Tier 1)             | Dữ liệu hiển thị                     |
|----------------|--------------------------------|---------------------------------------|---------------------------------------|
| Twitter / X    | `api.fxtwitter.com`            | `fxtwitter`, `vxtwitter`, `fixupx`    | Nội dung, ảnh, video, tương tác      |
| Reddit         | Reddit JSON API                | `rxddit`, `fxreddit`, `vxreddit`      | Tiêu đề, nội dung, ảnh, gallery       |
| TikTok         | `api.vxtiktok.com`             | `vxtiktok`, `tnktok`, `kktiktok`      | Mô tả, thumbnail, lượt tương tác     |
| Instagram      | `api.ddinstagram.com`          | `ddinstagram`, `eeinstagram`, `oginstagram` | Nội dung, ảnh/video             |
| Facebook       | Facebook oEmbed                | `facebed`, `fxfb`                     | Tiêu đề, tác giả                     |
| Bluesky        | `public.api.bsky.app`          | `bskx.app`, `fxbsky.app`              | Nội dung, ảnh, tương tác              |
| Twitch         | Twitch oEmbed                  | `fxtwitch`                            | Tiêu đề clip, thumbnail              |
| Pixiv          | `phixiv.net`                   | `phixiv.net`                          | Tiêu đề, ảnh, gallery, tag NSFW      |
| Threads        | Threads oEmbed                 | `fixthreads`, `vxthreads`             | Nội dung, ảnh/video, tác giả          |
| YouTube        | YouTube oEmbed                 | `koutube.com`                         | Tiêu đề, thumbnail video / Shorts    |

#### Pipeline xử lý URL 3 tầng (Multi-tier Pipeline):
1. **Tier 0 (API Fetchers)**: Gọi API JSON/oEmbed để trích xuất dữ liệu có cấu trúc và dựng Discord Embed giàu thông tin.
2. **Tier 1 (Proxy URL Chain)**: Nếu API thất bại, tự động duyệt chuỗi Proxy domain theo thứ tự ưu tiên (xác thực trước qua API / OpenGraph metadata).
3. **Tier 2 (yt-dlp Fallback)**: Nếu tất cả API và Proxy đều không khả dụng, sử dụng `yt-dlp` bóc tách media trực tiếp trong background thread.
4. **Webhook Emulation**: Tự động gửi bài viết qua Discord Webhook giả lập đúng avatar và tên người gửi gốc, đồng thời xoá tin nhắn thô ban đầu.

### Bộ lọc NSFW / Spoiler

Bot xử lý nội dung nhạy cảm (NSFW) và nội dung spoiler theo cấu hình của máy chủ:

- **`block`**: Chặn hoàn toàn, không hiển thị embed.
- **`spoiler`** (mặc định): Che ảnh bằng tag spoiler của Discord, hiển thị cảnh báo.
- **`allow`**: Hiển thị bình thường.

Nếu kênh được đánh dấu là kênh NSFW trong cài đặt Discord, nội dung nhạy cảm sẽ luôn hiển thị bình thường bất kể cấu hình.

### Hệ thống cấu hình phân cấp

Cấu hình được lưu trữ trong SQLite (`data/bot_config.db`) với mô hình phân cấp ba lớp:

```
Mặc định -> Ghi đè bởi Máy chủ -> Ghi đè bởi Kênh
```

Cài đặt của kênh có độ ưu tiên cao nhất. Nếu kênh không có cài đặt riêng, cấu hình máy chủ được áp dụng. Nếu máy chủ cũng không có, giá trị mặc định được sử dụng.

Dữ liệu cấu hình được cache trong bộ nhớ với TTL 300 giây.

### Web Dashboard

Giao diện web Flask hiển thị thông tin giám sát thời gian thực:

- Trạng thái bot (online/offline), uptime, độ trễ API.
- Số lượng máy chủ đang phục vụ, RAM sử dụng.
- Console log trực tiếp.
- Kết quả kiểm thử từ lệnh `/test_tomtat`.

### Graceful Shutdown

Khi nhận tín hiệu tắt (SIGTERM/SIGINT), bot hoãn tối đa 15 giây để hoàn thành các lệnh tóm tắt đang xử lý, gửi thông báo cho người dùng, sau đó đóng kết nối.

---

## Slash Commands

### `/tomtat`

Tóm tắt lịch sử trò chuyện của một kênh chat.

| Tham số        | Mô tả                                                      | Mặc định           |
|----------------|-------------------------------------------------------------|---------------------|
| `channel`      | Kênh cần tóm tắt                                           | Kênh hiện tại       |
| `hours`        | Quét tin nhắn trong X giờ qua (tối đa 168 giờ / 7 ngày)    | 2.0                 |
| `limit`        | Số lượng tin nhắn quét tối đa (tối đa 2500)                 | 150                 |
| `summary_type` | `short` (ngắn gọn) hoặc `long` (chi tiết kèm timeline)     | `short`             |
| `focus`        | Chủ đề hoặc từ khóa cần phân tích sâu                       | Không               |

Cooldown: 30 giây mỗi người dùng.

### `/test_tomtat`

Chạy tóm tắt thử nghiệm kèm AI tự động đánh giá chất lượng. Kết quả được gửi riêng (ephemeral) và lưu trên Web Dashboard. Tham số giống `/tomtat`.

### `/config view`

Xem cấu hình hiện tại đang áp dụng cho kênh, bao gồm trạng thái từng nền tảng, chế độ NSFW, và nguồn gốc của từng cài đặt (mặc định / máy chủ / kênh).

### `/config set`

Đặt cấu hình mặc định cho toàn máy chủ. Yêu cầu quyền `Manage Server`.

| Tham số | Mô tả                                                                   |
|---------|--------------------------------------------------------------------------|
| `key`   | `nsfw_mode` / `auto_embed_enabled` / `suppress_original_embed`           |
| `value` | Giá trị tương ứng (`block`/`spoiler`/`allow` hoặc `true`/`false`)       |

### `/config channel_set`

Đặt cấu hình riêng cho kênh hiện tại, ghi đè cấu hình máy chủ. Yêu cầu quyền `Manage Channels`. Tham số giống `/config set`.

### `/config channel_reset`

Xóa toàn bộ cấu hình riêng của kênh hiện tại, đưa về áp dụng cấu hình máy chủ. Yêu cầu quyền `Manage Channels`.

### `/config reset`

Reset toàn bộ cấu hình máy chủ về giá trị mặc định. Yêu cầu quyền `Administrator`.

### `/config platforms`

Mở giao diện chọn (dropdown) để bật hoặc tắt từng nền tảng mạng xã hội. Có thể áp dụng cho toàn máy chủ hoặc kênh hiện tại. Yêu cầu quyền `Manage Server`.

### `/proxy view`

Xem danh sách proxy domain đang áp dụng cho từng nền tảng (tuỳ chỉnh của server hoặc mặc định toàn cục). Yêu cầu quyền `Manage Server`.

### `/proxy set`

Thiết lập danh sách proxy domain ưu tiên cho một nền tảng trên máy chủ (phân cách bằng dấu phẩy, VD: `fxtwitter.com,vxtwitter.com`). Yêu cầu quyền `Manage Server`.

### `/proxy reset`

Khôi phục danh sách proxy domain của nền tảng về mặc định toàn cục. Yêu cầu quyền `Manage Server`.

---

## Cấu trúc dự án

```
DiscordMikeBot/
  app.py                  # Entry point tinh gọn: lifecycle bot, background runner, graceful shutdown
  bot_instance.py         # Khởi tạo SummaryBot, đồng bộ Slash Commands, tải extensions
  config.py               # Biến môi trường, hằng số AI, log redirection, state bộ đệm
  gunicorn.conf.py        # Cấu hình Gunicorn cho production
  render.yaml             # Cấu hình deploy trên Render
  requirements.txt        # Dependencies
  .env.example            # Mẫu file biến môi trường
  cogs/
    config_cog.py         # Nhóm lệnh /config (view, set, channel_set, reset, platforms)
    embed_cog.py          # Listener on_message, pipeline 3 tầng xử lý link mạng xã hội
    proxy_cog.py          # Nhóm lệnh /proxy (view, set, reset) quản lý proxy per-guild
    summary_cog.py        # Lệnh /tomtat và /test_tomtat tóm tắt AI
  services/
    ai_service.py         # Xử lý AI: Single-Pass, MapReduce, QA Evaluator
    config_manager.py     # Quản lý cấu hình SQLite, cache bộ nhớ, proxy domains
    embed_builder.py      # Xây dựng Discord Embed & Bộ lọc NSFW/Spoiler
    platform_fetchers.py  # Fetcher API trực tiếp (Twitter, Reddit, TikTok, Pixiv, Threads, YouTube...)
    platform_ui.py        # Nút liên kết "Xem trên [Nền tảng]"
    proxy_validator.py    # Xác thực proxy URL qua API & OG metadata (Chain of Responsibility)
    webhook_sender.py     # Giả lập người dùng gửi tin nhắn qua Discord Webhook
    ytdlp_fallback.py     # Fallback bóc tách media qua yt-dlp
  web/
    app.py                # Backend Flask Server & REST API endpoints
    templates/
      dashboard.html      # Giao diện Web Dashboard (HTML/CSS/JS tách riêng)
  utils/
    constants.py          # Registry nền tảng, regex patterns, proxy registry, helper functions
  data/
    bot_config.db         # SQLite database (tự động tạo, nằm trong .gitignore)
```

---

## Yêu cầu hệ thống

- Python 3.10+
- Discord Bot Token (từ [Discord Developer Portal](https://discord.com/developers/applications))
- Google Gemini API Key (từ [Google AI Studio](https://aistudio.google.com/))

## Cài đặt

1. Clone repository:

```bash
git clone https://github.com/<your-username>/DiscordMikeBot.git
cd DiscordMikeBot
```

2. Cài đặt dependencies:

```bash
pip install -r requirements.txt
```

3. Tạo file `.env` tại thư mục gốc (tham khảo `.env.example`):

```env
DISCORD_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_gemini_api_key
PORT=8080
```

4. Khởi chạy:

```bash
python app.py
```

Bot Discord và Flask Dashboard sẽ cùng khởi động. Dashboard mặc định chạy tại `http://localhost:8080`.

---

## Triển khai (Deployment)

Dự án được cấu hình sẵn để chạy trên Render hoặc các nền tảng PaaS hỗ trợ Gunicorn/Flask:

- `render.yaml`: Cấu hình dịch vụ Render.
- `gunicorn.conf.py`: 1 worker, 4 threads, timeout 120 giây (đủ thời gian để bot đăng nhập và đồng bộ slash commands).

Đặt các biến môi trường (`DISCORD_TOKEN`, `GEMINI_API_KEY`, `PORT`) trong phần Environment Variables của nền tảng deploy.

---

## Dependencies

| Package         | Mục đích                                   |
|-----------------|-------------------------------------------|
| `discord.py`    | Discord API wrapper                       |
| `google-genai`  | Google Gemini / Gemma API client          |
| `python-dotenv` | Đọc biến môi trường từ file `.env`        |
| `Flask`         | Web Dashboard                             |
| `gunicorn`      | WSGI server cho production                |
| `psutil`        | Đọc thông số hệ thống (RAM, CPU)         |
| `aiohttp`       | HTTP client cho các proxy API             |
| `aiosqlite`     | Async SQLite cho hệ thống cấu hình       |

---

## Quyền Discord & Hướng dẫn Cấp quyền (Bot Permissions & Setup)

Để bot hoạt động đầy đủ tất cả các tính năng (đặc biệt là tính năng giả lập Webhook và tự động xoá link thô), bot cần các quyền sau:

### 1. Danh sách quyền bắt buộc:
* **`Manage Webhooks` (Quản lý Webhook)**: Để tạo Webhook gửi bài viết giả lập Avatar & Tên của người dùng.
* **`Manage Messages` (Quản lý Tin nhắn)**: Để tự động xoá tin nhắn chứa link thô ban đầu sau khi gửi embed.
* **`View Channels` (Xem Kênh)** & **`Send Messages` (Gửi Tin nhắn)**: Để tương tác trong các kênh chat.
* **`Embed Links` (Nhúng Liên kết)**: Để gửi embed tóm tắt AI và bài viết mạng xã hội.
* **`Attach Files` (Đính kèm Tệp)**: Để gửi file spoiler hình ảnh khi gặp nội dung NSFW.
* **`Read Message History` (Đọc Lịch sử Tin nhắn)**: Để bot quét tin nhắn và tạo bản tóm tắt AI (`/tomtat`).
* **`Use Application Commands` (Sử dụng Lệnh Ứng dụng)**: Để chạy các Slash Commands (`/tomtat`, `/config`, `/proxy`).

---

### 2. Cách 1: Cấp quyền trực tiếp trong Server Discord (Nhanh nhất - Không cần mời lại bot)

Nếu bot đã ở trong server của bạn, bạn chỉ cần cấp quyền cho **Role của Bot**:

1. Mở **Server Settings (Cài đặt máy chủ)** $\rightarrow$ Chọn mục **Roles (Vai trò)**.
2. Tìm và bấm vào Role có tên của bot (ví dụ: `MikeDaBot`).
3. Chuyển sang tab **Permissions (Quyền hạn)**.
4. Bật các quyền sau:
   - ✅ **Manage Webhooks** (*Quản lý Webhook*)
   - ✅ **Manage Messages** (*Quản lý Tin nhắn*)
   - ✅ **Attach Files** (*Đính kèm Tệp*)
   - ✅ **Read Message History** (*Đọc Lịch sử Tin nhắn*)
   - ✅ **Embed Links** (*Nhúng Liên kết*)
   - *(Hoặc có thể bật quyền **Administrator** nếu là server cá nhân/nội bộ để bot có đầy đủ toàn quyền).*
5. Bấm **Save Changes (Lưu thay đổi)**.

> 💡 **Lưu ý về Channel Permissions**: Nếu một kênh cụ thể (ví dụ kênh `#💬chém-gió`) có cài đặt phân quyền riêng (Channel Overrides), hãy kiểm tra phần **Edit Channel (Chỉnh sửa kênh)** $\rightarrow$ **Permissions** để đảm bảo Role của Bot không bị dấu ❌ (gạch chéo đỏ) ở quyền **Manage Webhooks** hoặc **Manage Messages**.

---

### 3. Cách 2: Tạo Link Mời Bot mới có sẵn đầy đủ Quyền (Invite Link Generator)

Nếu bạn muốn tạo một đường link mời bot sang các máy chủ khác với đầy đủ quyền được chọn sẵn:

1. Truy cập [Discord Developer Portal](https://discord.com/developers/applications).
2. Chọn ứng dụng Bot của bạn (`MikeDaBot`).
3. **Bật Gateway Intents** (Bắt buộc):
   - Vào menu **Bot** ở thanh bên trái.
   - Cuộn xuống phần **Privileged Gateway Intents**.
   - Bật tích xanh: ✅ **MESSAGE CONTENT INTENT** và ✅ **SERVER MEMBERS INTENT**.
   - Bấm **Save Changes**.
4. **Tạo Link Mời (OAuth2 URL Generator)**:
   - Vào menu **OAuth2** $\rightarrow$ chọn **URL Generator**.
   - Trong mục **Scopes**, tích chọn:
     - ✅ `bot`
     - ✅ `applications.commands`
   - Trong mục **Bot Permissions** xuất hiện bên dưới, tích chọn:
     - ✅ *Manage Webhooks*
     - ✅ *Manage Messages*
     - ✅ *Read Messages/View Channels*
     - ✅ *Send Messages*
     - ✅ *Embed Links*
     - ✅ *Attach Files*
     - ✅ *Read Message History*
   - Copy đường dẫn ở ô **Generated URL** ở cuối trang và mở trên trình duyệt để thêm Bot vào Server.

*(Mẫu link mời nhanh - thay `CLIENT_ID_CUA_BAN` bằng Application ID của bạn):*
```
https://discord.com/oauth2/authorize?client_id=CLIENT_ID_CUA_BAN&permissions=2684423104&integration_type=0&scope=bot+applications.commands
```

---

## Giấy phép

Liên hệ tác giả để biết thêm thông tin về giấy phép sử dụng.

