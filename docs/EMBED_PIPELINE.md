# Social Embed Pipeline

Tài liệu vận hành pipeline preview mạng xã hội của Asumi. Cập nhật cho **v2.8.2 (2026-10-04)**.

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
   - **Facebook là ngoại lệ:** không tự động rơi xuống yt-dlp.

## Facebook manual fallback

### Vì sao không auto-fallback

Discord unfurl và Facebook share redirect không hoàn toàn đồng bộ với quá trình polling của bot. Một preview Facebed có thể render được ở client nhưng server fetch của bot vẫn trả `unfurl_timeout`. Nếu bot tự fallback ngay, preview video tốt có thể bị xóa rồi thay bằng thumbnail/card kém hơn.

Generic/login card ở poll sớm vì vậy **không fail-fast**. Asumi chờ hết grace window để Discord có cơ hội nâng cấp card thành preview/video thật.

### Hành vi v2.8.2

- Preview Facebook có nút Discord **↪️ Fallback**.
- Nút dùng Discord Interaction trực tiếp, không phụ thuộc web dashboard, public URL hay JavaScript.
- **Chỉ người gửi link gốc** mới bấm được. Người khác bấm sẽ nhận phản hồi ephemeral và không chạy fallback.
- Nếu Facebed đã gửi nhưng kết quả chỉ là `unfurl_timeout`, Asumi giữ preview hiện tại và trả trạng thái nội bộ `action_required`.
- Nếu proxy thất bại rõ ràng, Asumi gửi một prompt gọn với nút **Fallback** thay vì tự gọi yt-dlp.
- Khi người gửi bấm nút:
  - nút được disable ngay để hạn chế double-click;
  - Asumi chạy yt-dlp cho đúng origin message và URL;
  - nếu preview mới gửi thành công thì mới dọn preview/prompt cũ của **đúng URL đó**;
  - nếu fallback thất bại, nút được bật lại và preview hiện tại vẫn được giữ.
- Fallback được serialize bằng lock per-origin và dedupe theo `(origin_message_id, url)`.

## Vì sao bỏ hyperlink của v2.8.1

v2.8.1 thử dùng masked hyperlink trỏ về web route của Asumi. Cách đó phụ thuộc public host, browser/JavaScript và không có Discord Interaction identity, nên không đủ tin cậy cho thao tác này.

v2.8.2 bỏ hoàn toàn:

- `features/embed/manual_fallback.py`;
- `ASUMI_PUBLIC_URL` / `PUBLIC_BASE_URL`;
- web routes `/embed/fallback/<token>` và `/api/embed/fallback/<token>`.

Fallback giờ chạy hoàn toàn trong Discord.

## Lifecycle và cleanup

- Preview của bot vẫn được map về origin message để tự xóa khi origin bị xóa.
- Các preview có nút fallback được map thêm theo `(origin_id, url)`.
- Manual fallback chỉ cleanup các preview đã đăng ký cho đúng URL, tránh xóa nhầm khi một message chứa nhiều social links.
- Nếu yt-dlp không tạo được replacement thành công, không cleanup preview cũ.

## Regression checks

Các case cần giữ khi chỉnh embed pipeline:

- Facebook `unfurl_timeout` không được xóa preview và không được gọi yt-dlp tự động.
- Generic/login card Facebook ở poll sớm vẫn phải được chờ hết grace window.
- Preview Facebook phải có `FacebookFallbackView` với nút **Fallback**.
- User khác origin author không được trigger fallback.
- Origin author bấm nút phải gọi manual yt-dlp flow.
- Manual fallback thành công mới dọn preview cũ và chỉ dọn đúng URL.
- NSFW block không được rơi xuống manual/automatic fallback.
- Twitter/X và các nền tảng ngoài Facebook vẫn giữ automatic yt-dlp fallback.
- Original embed chỉ suppress khi pipeline đã xử lý được, bị block, hoặc đang ở trạng thái `action_required`.
