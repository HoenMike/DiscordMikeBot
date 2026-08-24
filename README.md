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

| Nền tảng       | Dịch vụ proxy sử dụng          | Dữ liệu hiển thị                     |
|----------------|--------------------------------|---------------------------------------|
| Twitter / X    | `api.fxtwitter.com`            | Nội dung, ảnh, video, lượt tương tác  |
| Reddit         | Reddit JSON API                | Tiêu đề, nội dung, ảnh, gallery       |
| TikTok         | `api.vxtiktok.com`             | Mô tả, thumbnail, lượt tương tác     |
| Instagram      | `api.ddinstagram.com`          | Nội dung, ảnh/video                   |
| Facebook       | Facebook oEmbed                | Tiêu đề, tác giả                     |
| Bluesky        | `public.api.bsky.app`          | Nội dung, ảnh, lượt tương tác         |
| Twitch         | Twitch oEmbed                  | Tiêu đề clip, thumbnail              |
| Pixiv          | `phixiv.net`                   | Tiêu đề, ảnh, gallery, tag NSFW      |

Tất cả đều sử dụng các dịch vụ proxy nhẹ, không phụ thuộc vào `yt-dlp` hay API key riêng của từng nền tảng.

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
    embed_cog.py          # Listener on_message, phát hiện URL mạng xã hội, tạo embed
    summary_cog.py        # Lệnh /tomtat và /test_tomtat tóm tắt AI
  services/
    ai_service.py         # Xử lý AI: Single-Pass, MapReduce, QA Evaluator
    config_manager.py     # Quản lý cấu hình SQLite, in-memory cache, deep merge
    embed_builder.py      # Xây dựng Discord Embed & Bộ lọc NSFW/Spoiler
    platform_fetchers.py  # Fetcher dữ liệu mạng xã hội (Twitter, Reddit, TikTok, Pixiv...)
  web/
    app.py                # Backend Flask Server & REST API endpoints
    templates/
      dashboard.html      # Giao diện Web Dashboard (HTML/CSS/JS tách riêng)
  utils/
    constants.py          # Registry nền tảng, regex patterns, cấu hình mặc định
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

## Quyền Discord (Bot Permissions)

Bot cần các quyền sau trong máy chủ Discord:

- `Read Messages` / `View Channels`
- `Send Messages`
- `Embed Links`
- `Attach Files`
- `Read Message History`
- `Manage Messages` (để ẩn embed mặc định)
- `Use Slash Commands`

**Intent bắt buộc**: `Message Content Intent` (bật trong Discord Developer Portal).

---

## Giấy phép

Liên hệ tác giả để biết thêm thông tin về giấy phép sử dụng.
