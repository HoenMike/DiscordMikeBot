# MikeDaBot

Bot Discord tích hợp AI (Gemini / Gemma 4) chuyên tóm tắt lịch sử trò chuyện và tự động nhúng nội dung mạng xã hội với hệ thống fallback đa tầng.

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

Bot tự động phát hiện các URL mạng xã hội trong tin nhắn và tạo embed tuỳ chỉnh thay thế embed mặc định của Discord. Người dùng chỉ cần dán link, không cần sử dụng lệnh.

Hệ thống xử lý theo kiến trúc **Chain of Responsibility** với ba tầng fallback tuần tự. Nếu tầng trước thất bại, tầng sau sẽ được thử tự động cho đến khi thành công hoặc hết phương án.

#### Tier 0 -- API Fetcher (dữ liệu có cấu trúc)

Gọi trực tiếp JSON API của các dịch vụ proxy (VD: `api.fxtwitter.com`, `api.vxtiktok.com`) để lấy dữ liệu có cấu trúc: nội dung bài viết, media URL, thống kê tương tác, thông tin tác giả. Dữ liệu được dùng để xây dựng Discord Embed chi tiết với đầy đủ thông tin.

#### Tier 1 -- Proxy Chain Validation (xác thực OG metadata)

Duyệt tuần tự danh sách proxy domain theo thứ tự ưu tiên giảm dần. Với mỗi proxy:

1. Viết lại URL gốc sang proxy domain (VD: `twitter.com` -> `fxtwitter.com`).
2. Nếu proxy có JSON API: xác thực qua API trước.
3. Nếu không có API hoặc API thất bại: gửi HTTP request tới proxy URL, đọc 16KB đầu tiên, phân tích HTML tìm OpenGraph / Twitter Card meta tags (`og:image`, `og:video`, `twitter:card`).
4. Proxy đầu tiên trả về metadata hợp lệ sẽ được sử dụng. URL đã viết lại được gửi trực tiếp qua webhook.

Danh sách proxy mặc định có thể được ghi đè cho từng máy chủ thông qua lệnh `/proxy set`.

#### Tier 2 -- yt-dlp Fallback (trích xuất media trực tiếp)

Khi cả API lẫn proxy chain đều thất bại, bot sử dụng `yt-dlp` để trích xuất URL media trực tiếp từ trang gốc. Quá trình chạy trong thread riêng (`asyncio.to_thread()`) với timeout cố định để không chặn event loop. Embed tạo từ yt-dlp tự động áp dụng màu thương hiệu và icon của nền tảng tương ứng.

Toàn bộ pipeline được bọc trong `asyncio.wait_for()` với timeout 45 giây.

#### Nền tảng được hỗ trợ

| Nền tảng    | API Fetcher (Tier 0)      | Proxy Chain (Tier 1)                                  |
|-------------|---------------------------|-------------------------------------------------------|
| Twitter / X | `api.fxtwitter.com`       | `fxtwitter.com`, `vxtwitter.com`, `fixupx.com`        |
| Reddit      | Reddit JSON API           | `rxddit.com`, `fxreddit.seria.moe`, `vxreddit.com`    |
| TikTok      | `api.vxtiktok.com`        | `vxtiktok.com`, `tnktok.com`, `kktiktok.com`          |
| Instagram   | `api.ddinstagram.com`     | `ddinstagram.com`, `eeinstagram.com`, `oginstagram.com` |
| Facebook    | Facebook oEmbed           | `facebed.seria.moe`, `fxfb.seria.moe`                |
| Bluesky     | `public.api.bsky.app`     | `bskx.app`, `fxbsky.app`                             |
| Twitch      | Twitch oEmbed             | `fxtwitch.seria.moe`                                 |
| Pixiv       | `phixiv.net`              | `phixiv.net`                                         |
| Threads     | Threads oEmbed            | `fixthreads.seria.moe`, `vxthreads.net`              |
| YouTube     | YouTube oEmbed            | `koutube.com`                                        |

Tất cả 10 nền tảng đều được hỗ trợ qua cả ba tầng fallback. Tier 2 (yt-dlp) hoạt động chung cho mọi nền tảng mà yt-dlp hỗ trợ.

#### Giao diện theo nền tảng (Platform-Specific UI)

Mỗi tin nhắn embed đều đính kèm một `discord.ui.View` chứa nút liên kết (`ButtonStyle.link`) tới bài viết gốc, với nhãn phù hợp theo nền tảng:

| Nền tảng    | Nhãn nút                   |
|-------------|-----------------------------|
| Twitter / X | Xem bản gốc trên X         |
| TikTok      | Xem trên TikTok             |
| Reddit      | Xem trên Reddit             |
| Instagram   | Xem trên Instagram          |
| Bluesky     | Xem trên Bluesky            |
| YouTube     | Xem trên YouTube            |
| ...         | (tương tự cho các nền tảng khác) |

Embed tạo từ Tier 0 và Tier 2 tự động áp dụng màu thương hiệu (`color`) và icon (`icon_url`) của nền tảng tương ứng, được định nghĩa trong `utils/constants.py`.

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

Bot sử dụng kết nối SQLite persistent (WAL mode) thay vì mở/đóng trên mỗi query. Dữ liệu cấu hình được cache trong bộ nhớ theo ba tầng riêng biệt (guild, channel, proxy domains) với TTL 300 giây.

### Hệ thống gửi tin nhắn (Webhook Sender)

Tin nhắn embed được gửi qua webhook giả lập người dùng gốc. Chuỗi fallback khi gặp lỗi:

1. Gửi qua webhook (ưu tiên).
2. Nếu webhook bị xoá (`NotFound`): xoá cache, thử tạo lại.
3. Nếu không có quyền webhook (`Forbidden`): fallback sang `message.reply()`.
4. Nếu reply thất bại: fallback sang `channel.send()`.

Nội dung (`content`) vượt quá 2000 ký tự sẽ tự động bị cắt ngắn.

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

Xoá toàn bộ cấu hình riêng của kênh hiện tại, đưa về áp dụng cấu hình máy chủ. Yêu cầu quyền `Manage Channels`.

### `/config reset`

Reset toàn bộ cấu hình máy chủ về giá trị mặc định. Yêu cầu quyền `Administrator`.

### `/config platforms`

Mở giao diện chọn (dropdown) để bật hoặc tắt từng nền tảng mạng xã hội. Có thể áp dụng cho toàn máy chủ hoặc kênh hiện tại. Yêu cầu quyền `Manage Server`.

### `/proxy view`

Xem danh sách proxy đang được sử dụng cho một nền tảng cụ thể, bao gồm thứ tự ưu tiên. Hiển thị rõ danh sách đang là tuỳ chỉnh hay mặc định. Yêu cầu quyền `Manage Server`.

| Tham số    | Mô tả                                   |
|------------|------------------------------------------|
| `platform` | Nền tảng cần xem (dropdown có autocomplete) |

### `/proxy set`

Ghi đè danh sách proxy fallback cho một nền tảng bằng danh sách tuỳ chỉnh. Các domain được phân cách bằng dấu phẩy, thử theo thứ tự từ trái sang phải. Tối đa 10 domain mỗi nền tảng. Yêu cầu quyền `Manage Server`.

| Tham số    | Mô tả                                                                          |
|------------|---------------------------------------------------------------------------------|
| `platform` | Nền tảng cần thay đổi                                                           |
| `domains`  | Danh sách domain, phân cách bằng dấu phẩy (VD: `fxtwitter.com,vxtwitter.com`)  |

### `/proxy reset`

Khôi phục danh sách proxy của một nền tảng về mặc định toàn cục, xoá cấu hình tuỳ chỉnh. Yêu cầu quyền `Manage Server`.

| Tham số    | Mô tả                          |
|------------|---------------------------------|
| `platform` | Nền tảng cần khôi phục mặc định |

---

## Cấu trúc dự án

```
MikeDaBot/
  app.py                    # Điểm khởi chạy, đăng ký slash commands, graceful shutdown
  bot_instance.py           # Khởi tạo SummaryBot, tải cogs
  config.py                 # Biến môi trường, log redirection, đường dẫn database
  ai_helper.py              # Xử lý AI: prompt engineering, MapReduce, QA evaluator
  web_dashboard.py          # Flask dashboard (HTML/CSS/JS inline)
  gunicorn.conf.py          # Cấu hình Gunicorn cho production
  render.yaml               # Cấu hình deploy trên Render
  requirements.txt          # Dependencies
  .env.example              # Mẫu file biến môi trường
  cogs/
    config_cog.py           # Nhóm lệnh /config (view, set, reset, platforms)
    embed_cog.py            # Listener on_message, pipeline fallback 3 tầng
    proxy_cog.py            # Nhóm lệnh /proxy (view, set, reset)
  services/
    config_manager.py       # Quản lý cấu hình SQLite, cache phân tầng, CRUD proxy domains
    embed_builder.py        # Xây dựng Discord Embed thống nhất
    nsfw_filter.py          # Bộ lọc NSFW / Spoiler
    platform_fetchers.py    # Hàm fetch dữ liệu từ các nền tảng qua API (Tier 0)
    platform_ui.py          # discord.ui.View với nút liên kết theo nền tảng
    proxy_validator.py      # Xác thực proxy qua JSON API và OG metadata (Tier 1)
    webhook_sender.py       # Gửi tin nhắn qua webhook với chuỗi fallback
    ytdlp_fallback.py       # Trích xuất media bằng yt-dlp trong thread riêng (Tier 2)
  utils/
    constants.py            # Registry nền tảng, proxy domains, regex patterns, cấu hình mặc định
  data/
    bot_config.db           # SQLite database (tự động tạo, nằm trong .gitignore)
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
- `gunicorn.conf.py`: 1 worker, 4 threads, timeout 120 giây.

Đặt các biến môi trường (`DISCORD_TOKEN`, `GEMINI_API_KEY`, `PORT`) trong phần Environment Variables của nền tảng deploy.

---

## Dependencies

| Package         | Mục đích                                                  |
|-----------------|-----------------------------------------------------------|
| `discord.py`    | Discord API wrapper                                       |
| `google-genai`  | Google Gemini / Gemma API client                          |
| `python-dotenv` | Đọc biến môi trường từ file `.env`                        |
| `Flask`         | Web Dashboard                                             |
| `gunicorn`      | WSGI server cho production                                |
| `psutil`        | Đọc thông số hệ thống (RAM, CPU)                         |
| `aiohttp`       | HTTP client bất đồng bộ cho API fetcher và proxy validator |
| `aiosqlite`     | Async SQLite cho hệ thống cấu hình và proxy domains      |
| `yt-dlp`        | Trích xuất media trực tiếp, fallback tầng cuối (Tier 2)  |

---

## Quyền Discord (Bot Permissions)

Bot cần các quyền sau trong máy chủ Discord:

- `Read Messages` / `View Channels`
- `Send Messages`
- `Embed Links`
- `Attach Files`
- `Read Message History`
- `Manage Messages` (để xoá tin nhắn gốc và ẩn embed mặc định)
- `Manage Webhooks` (để tạo và sử dụng webhook giả lập người dùng)
- `Use Slash Commands`

**Intent bắt buộc**: `Message Content Intent` (bật trong Discord Developer Portal).

---

## Giấy phép

Liên hệ tác giả để biết thêm thông tin về giấy phép sử dụng.
