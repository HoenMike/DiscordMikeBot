# Social Embed Pipeline

Tài liệu vận hành pipeline preview mạng xã hội của Asumi. Cập nhật cho **v2.8.4 (2026-10-04)**.

## Mục tiêu

Asumi ưu tiên native embed của Discord khi một proxy có thể tự unfurl video/media. Với Facebook, bot không cố đoán thay người dùng xem proxy hiện tại có "đủ tốt" hay không: bot gửi đúng raw proxy URL, còn việc đổi proxy là thao tác thủ công qua button.

## Pipeline chung

1. **Tier 0 — API fetcher**
   - Dùng API/oEmbed có cấu trúc khi nền tảng hỗ trợ.
   - Facebook hiện không có unauthenticated API fetcher phù hợp nên thường đi thẳng Tier 1.

2. **Tier 1 — Proxy**
   - Proxy được lấy từ `PROXY_DOMAINS` hoặc guild override.
   - Các candidate có thể được pre-validate bằng API/OpenGraph trước khi gửi.
   - Với Twitter/TikTok/Instagram/Reddit/... flow cũ vẫn có thể tự thử proxy tiếp theo nếu candidate gửi ra không dùng được.
   - Với **Facebook**, sau khi tìm được một candidate và gửi thành công thì **dừng**: không tự roll sang proxy khác.

3. **Tier 2 — yt-dlp**
   - Dùng cho Twitter/X, TikTok, Instagram, Reddit và Twitch khi các tầng trước thất bại.
   - **Facebook không nằm trong yt-dlp fallback path từ v2.8.3.**

## Facebook: compact masked proxy link

Facebook preview hiện dùng masked markdown link để tránh lộ URL dài trong chat:

```text
Trả lời @user • [facebed.seria.moe](https://facebed.seria.moe/share/r/...)
```

Điểm quan trọng là URL đích **không** được bọc bằng `<...>`. Discord dùng dạng `[label](url)` cho masked link, còn `[label](<url>)` là dạng suppress preview. Vì vậy Asumi giữ URL proxy trực tiếp trong target của masked link để Discord vẫn có thể unfurl, nhưng phần người dùng nhìn thấy chỉ còn domain proxy.

Nếu nội dung cần spoiler, Asumi bọc **toàn bộ masked link** trong spoiler:

```text
||[facebed.seria.moe](https://facebed.seria.moe/share/r/...)||
```

Button **🔄 Proxy khác** vẫn chỉ là component phụ; nó không chịu trách nhiệm tạo embed.

## Facebook proxy roll

Preview Facebook gắn `FacebookFallbackView` với button **🔄 Proxy khác**.

### Quyền sử dụng

- Payload giữ `origin_id`, `channel_id`, `author_id`, original URL, spoiler state và danh sách proxy đã thử.
- `interaction_check` chỉ cho đúng `author_id` của origin message dùng button.
- User khác nhận phản hồi ephemeral và không thay đổi preview.

### Khi bấm Proxy khác

1. Button hiện tại disable ngay để hạn chế double-click.
2. Asumi fetch lại origin message và xác minh:
   - message vẫn tồn tại;
   - author vẫn đúng;
   - original URL vẫn còn trong message.
3. Ghép danh sách `tried_domains` từ payload với state server theo `(origin_message_id, URL)`.
4. `find_valid_proxy(... excluded_domains=tried)` tìm candidate kế tiếp.
5. Nếu có candidate:
   - gửi **message mới chứa masked proxy link** và một button mới mang state đã cập nhật;
   - chỉ sau khi gửi mới thành công mới xóa preview proxy cũ;
   - log `manual_proxy_roll`.
6. Nếu không còn candidate:
   - không gọi yt-dlp;
   - giữ preview hiện tại;
   - button đổi thành trạng thái **Hết proxy** và user nhận thông báo ephemeral.

## Vì sao không server-side auto-roll Facebook

Discord client có thể render/unfurl khác thời điểm với polling của bot. Một server-side classifier có thể nhìn thấy timeout/generic card trong khi client vừa dựng được video đúng. Nếu bot tự xóa message proxy và thay candidate khác, nó có thể phá một preview đang hoạt động.

v2.8.3 vì vậy dùng quy tắc đơn giản:

- **send compact masked proxy link**;
- **không auto-roll sau send**;
- **user quyết định khi nào cần proxy khác**.

Các helper verify unfurl vẫn còn cho flow của nền tảng khác và regression coverage, nhưng không quyết định rotation sau khi Facebook proxy đã được gửi.

## State và cleanup

- Mapping chung `_origin_to_preview_map` tiếp tục đảm bảo xóa preview khi origin message bị xóa.
- `_facebook_proxy_roll_state[(origin_id, url)]` giữ set domain đã thử.
- `_manual_fallback_previews[(origin_id, url)]` giữ preview liên quan đúng URL đó.
- Khi roll thành công, cleanup chỉ tác động preview cũ của cùng URL; message có nhiều social link không bị xóa chéo.
- Nếu message proxy mới gửi thất bại, preview hiện tại không bị xóa.

## Regression checks

Các case cần giữ khi chỉnh pipeline:

- Facebook proxy message phải chứa masked link `[domain](proxy-url)` và không bọc URL đích bằng `<...>`, để tránh suppress unfurl.
- Sau khi proxy Facebook đầu tiên đã gửi, `_verify_proxy_unfurl` không được tự kích hoạt rotation.
- Preview Facebook phải có `FacebookFallbackView` / button **Proxy khác**.
- User khác origin author không được roll proxy.
- Origin author bấm button phải tìm proxy kế tiếp bằng excluded/tried state.
- Manual proxy roll không được gọi `_try_ytdlp_fallback`.
- Facebook phải bị loại khỏi supported platform list của yt-dlp fallback.
- Proxy cũ chỉ bị cleanup sau khi proxy mới gửi thành công.
- Khi hết proxy, giữ preview hiện tại.
- Twitter/X và các nền tảng ngoài Facebook vẫn giữ automatic yt-dlp fallback hiện tại.
