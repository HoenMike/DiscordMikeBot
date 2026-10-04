# Social Embed Pipeline

Tài liệu vận hành pipeline preview mạng xã hội của Asumi. Cập nhật cho **v2.8.1 (2026-10-04)**.

## Mục tiêu

Asumi ưu tiên giữ preview tốt nhất mà Discord đã/đang render, tránh thay một preview có video bằng fallback kém chất lượng chỉ vì quá trình kiểm tra server-side kết thúc sớm hơn Discord unfurl.

## Pipeline chung

1. **Tier 0 — API fetcher**
   - Dùng API/oEmbed có cấu trúc khi nền tảng hỗ trợ.
   - Nếu tạo được preview hợp lệ thì gửi ngay.

2. **Tier 1 — Proxy chain**
   - Duyệt proxy theo thứ tự trong `PROXY_DOMAINS`.
   - Xác thực metadata trước khi gửi.
   - Sau khi gửi, Asumi fetch lại message Discord trong cửa sổ bounded grace period để xem unfurl có dùng được hay không.

3. **Tier 2 — yt-dlp**
   - Twitter/X, TikTok, Instagram, Reddit và Twitch vẫn tự động rơi xuống yt-dlp nếu Tier 0/1 thất bại.
   - **Facebook là ngoại lệ từ v2.8.1:** không tự động rơi xuống yt-dlp.

## Facebook v2.8.1

### Vì sao thay đổi

Discord unfurl và Facebook share redirect không hoàn toàn đồng bộ với quá trình polling của bot. Một preview Facebed có thể render được ở client nhưng server fetch của bot vẫn trả `unfurl_timeout`. Trước v2.8.1, bot xóa preview này và tự gửi yt-dlp fallback, dẫn tới card tĩnh/thumbnail thiếu video.

### Hành vi mới

- Preview Facebook do API/proxy tạo ra có hyperlink **`[fallback]`** nhỏ gọn.
- Nếu Discord xác minh được preview: giữ nguyên như bình thường.
- Nếu Facebed đã gửi nhưng kết quả chỉ là `unfurl_timeout`:
  - giữ preview hiện tại;
  - trả trạng thái nội bộ `action_required`;
  - không gọi yt-dlp tự động.
- Nếu các proxy thất bại rõ ràng:
  - gửi một prompt rất gọn chỉ chứa reply context và `[fallback]`;
  - vẫn không gọi yt-dlp tự động.
- Khi hyperlink được kích hoạt:
  - Asumi chạy yt-dlp cho đúng message gốc;
  - nếu gửi preview mới thành công thì mới dọn preview/prompt cũ;
  - nếu thất bại thì preview hiện tại vẫn được giữ.

## Hyperlink manual fallback

Discord masked hyperlink không có interaction identity như Discord Button. Vì vậy v2.8.1 dùng một URL ký, ngắn hạn và gắn chặt với:

- origin message ID;
- channel ID;
- author ID của message gốc;
- platform;
- original URL;
- spoiler state.

Token dùng `FLASK_SECRET_KEY` và hết hạn sau **15 phút**.

Route GET `/embed/fallback/<token>` **không thay đổi trạng thái**. Trang này dùng JavaScript gửi POST tới `/api/embed/fallback/<token>`. Cách này tránh Discord crawler/link preview hoặc bot indexer vô tình kích hoạt fallback chỉ bằng việc fetch hyperlink.

Ở bước chạy fallback, Asumi fetch lại origin message và kiểm tra:

- message vẫn tồn tại;
- author của origin message vẫn khớp author ID trong token;
- URL trong token vẫn có trong nội dung message.

Lưu ý: masked hyperlink trong một message công khai không thể xác thực danh tính người đang dùng trình duyệt nếu không thêm Discord OAuth. Vì vậy author ID ở đây dùng để ràng buộc fallback với đúng **origin message**, không phải để chứng minh browser click đến từ đúng Discord account. Với server cần kiểm soát chặt hơn, nên dùng Discord Interaction hoặc OAuth thay vì hyperlink thuần.

## Public URL

Asumi tạo hyperlink theo thứ tự:

1. `ASUMI_PUBLIC_URL`
2. `RENDER_EXTERNAL_URL`
3. nếu cả hai không có, manual hyperlink không được tạo.

Trên Render thường không cần cấu hình thêm. Ở host khác, đặt:

```env
ASUMI_PUBLIC_URL=https://asumi.example.com
```

## Regression checks

Các case cần giữ khi chỉnh embed pipeline:

- Facebook `unfurl_timeout` không được xóa preview và không được gọi yt-dlp tự động.
- Facebook generic/login card vẫn được phép thử proxy tiếp theo.
- Manual fallback thành công mới dọn preview cũ.
- NSFW block không được rơi xuống manual/automatic fallback.
- Twitter/X và các nền tảng ngoài Facebook vẫn giữ automatic yt-dlp fallback.
- Original embed chỉ suppress khi pipeline đã xử lý được, bị block, hoặc đang ở trạng thái `action_required`.
