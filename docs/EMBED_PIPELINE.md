# Social Embed Pipeline

Tài liệu vận hành pipeline preview mạng xã hội của Asumi. Cập nhật cho **v3.10.1 (2026-10-09)**. Giữ UX owner-only của v2.8.5, khôi phục fallback video an toàn.

## Mục tiêu

Asumi ưu tiên native embed của Discord khi một proxy có thể tự unfurl video/media. Mọi preview do Asumi tạo đều có cùng bộ điều khiển owner-only **🔄 Reload** và **🗑️ Bỏ embed**. Với Facebook, Reload vẫn là thao tác roll proxy thủ công; bot không tự đoán thay người dùng xem proxy hiện tại có "đủ tốt" hay không.

## Pipeline chung

1. **Tier 0 — API fetcher**
   - Dùng API/oEmbed có cấu trúc khi nền tảng hỗ trợ.
   - Facebook hiện không có unauthenticated API fetcher phù hợp nên thường đi thẳng Tier 1.

2. **Tier 1 — Proxy**
   - Proxy được lấy từ `PROXY_DOMAINS` hoặc guild override.
   - Các candidate có thể được pre-validate bằng API/OpenGraph trước khi gửi.
   - Với Twitter/TikTok/Instagram/Reddit/... flow cũ vẫn có thể tự thử proxy tiếp theo nếu candidate gửi ra không dùng được.
   - Với **Facebook**, thử các provider theo thứ tự `facebed.com` → `facebed.seria.moe` → `facecot.com` → `fixacebook.com` (có thể cấu hình override theo guild). Chỉ chấp nhận video nếu metadata có video/player thật, không dùng mỗi ảnh thumbnail hay login card. Sau khi gửi thành công vẫn **dừng**, giữ quyền chọn Reload thủ công.

3. **Tier 2 — yt-dlp**
   - Dùng cho Twitter/X, TikTok, Instagram, Reddit và Twitch khi các tầng trước thất bại.
   - **Facebook `/share/v/`, `/share/r/`, Reel, Watch, Video** được thử yt-dlp **cuối cùng** khi không có proxy hợp lệ hoặc chủ link bấm Reload mà các proxy còn lại thất bại. Chỉ gửi kết quả nếu tải được **file video thật** trong giới hạn Discord; không coi ảnh poster Facebook login là video. Bài Facebook dạng post thường không gọi yt-dlp.

## Facebook: compact masked proxy link

Facebook preview hiện dùng masked markdown link để tránh lộ URL dài trong chat:

```text
Trả lời @user • [facebed.seria.moe](https://facebed.seria.moe/share/v/...)
```

Điểm quan trọng là URL đích **không** được bọc bằng `<...>`. Discord dùng dạng `[label](url)` cho masked link, còn `[label](<url>)` là dạng suppress preview. Vì vậy Asumi giữ URL proxy trực tiếp trong target của masked link để Discord vẫn có thể unfurl, nhưng phần người dùng nhìn thấy chỉ còn domain proxy.

Nếu nội dung cần spoiler, Asumi bọc **toàn bộ masked link** trong spoiler:

```text
||[facebed.seria.moe](https://facebed.seria.moe/share/v/...)||
```

Buttons **🔄 Reload** và **🗑️ Bỏ embed** chỉ là component điều khiển; chúng không chịu trách nhiệm tạo unfurl.

## Universal preview actions (v2.8.5)

Mọi preview từ Tier 0, Tier 1 và Tier 2 gắn `EmbedActionView` với hai button:

- **🔄 Reload**: chỉ người gửi link gốc được dùng.
  - Facebook: thử proxy tiếp theo theo state `tried_domains`; chỉ khi không còn proxy hợp lệ mới thử yt-dlp với URL video công khai.
  - Provider khác: chạy lại pipeline cho đúng URL; preview hiện tại chỉ bị xóa sau khi replacement tạo thành công.
- **🗑️ Bỏ embed**: chỉ người gửi link gốc được dùng. Asumi unsuppress message gốc để Discord dựng native embed rồi dọn toàn bộ preview Asumi thuộc origin message.

Discord chỉ cho suppress/unsuppress ở cấp **message**, không theo từng URL. Vì vậy với message chứa nhiều social URL, Bỏ embed revert toàn bộ origin message thay vì chỉ xóa một preview; cách này tránh native preview và Asumi preview bị trùng nhau.

Cả interaction layer và server-side handler đều kiểm tra lại `author_id`, origin message và original URL trước khi thay đổi trạng thái.

## Facebook proxy roll

Preview Facebook gắn `EmbedActionView`. Nút **🔄 Reload** gọi manual proxy roll hiện có; nút **🗑️ Bỏ embed** dùng universal native-revert flow.

### Quyền sử dụng

- Payload giữ `origin_id`, `channel_id`, `author_id`, original URL, spoiler state và danh sách proxy đã thử.
- `interaction_check` chỉ cho đúng `author_id` của origin message dùng Reload/Bỏ embed.
- User khác nhận phản hồi ephemeral và không thay đổi preview.

### Khi bấm Reload trên Facebook

1. Button hiện tại disable ngay để hạn chế double-click.
2. Asumi fetch lại origin message và xác minh:
   - message vẫn tồn tại;
   - author vẫn đúng;
   - original URL vẫn còn trong message.
3. Ghép danh sách `tried_domains` từ payload với state server theo `(origin_message_id, URL)`.
4. `find_valid_proxy(... excluded_domains=tried)` tìm candidate kế tiếp; validation failure/timeout không khóa domain vĩnh viễn.
5. Nếu có candidate:
   - gửi **message mới chứa masked proxy link** và một button mới mang state đã cập nhật;
   - chỉ sau khi gửi mới thành công mới xóa preview proxy cũ;
   - log `manual_proxy_roll`.
6. Nếu không còn candidate: thử yt-dlp video-only cuối cùng; nếu có file video thật, gửi preview mới rồi mới xóa preview cũ. Nếu thất bại, **giữ preview cũ**, nêu lý do tạm lỗi/hết proxy và giữ nút mở Facebook gốc. Không thử tự động vô hạn hoặc sử dụng cookies đăng nhập.

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
- Preview mọi provider phải có `EmbedActionView` với **Reload** + **Bỏ embed**.
- User khác origin author không được dùng cả hai action.
- Reload Facebook phải tìm proxy kế tiếp bằng excluded/tried state; Reload provider khác phải re-run đúng URL và giữ preview cũ nếu replacement thất bại.
- Bỏ embed phải unsuppress origin message và cleanup preview Asumi của origin để không tạo duplicate.
- Manual proxy roll chỉ gọi `_try_ytdlp_fallback` sau khi không còn proxy hợp lệ, cho đường dẫn video Facebook và chỉ với video thật.
- Facebook bài viết không phải video vẫn phải bị loại khỏi yt-dlp fallback; video chỉ được coi thành công nếu file đính kèm tải được.
- Proxy cũ chỉ bị cleanup sau khi proxy mới gửi thành công.
- Khi hết proxy và yt-dlp thất bại, giữ preview hiện tại; lỗi tạm thời có cooldown và không được xem là vĩnh viễn.
- Twitter/X và các nền tảng ngoài Facebook vẫn giữ automatic yt-dlp fallback hiện tại.


## v3.10.1 — Incident Facebook shared video & acceptance

- **Root cause from code review:** `build_proxy_url()` rewrote a Facebook `/share/v/{token}` video share path into `/share/r/{token}` Reel path, silently changing the lookup type. Preserve the literal path and query. Numeric `/reel/{id}` paths still normalize to `/watch?v={id}` as before.
- For Facebook **video** paths, OG validation accepts only a real video/player tag; image-only cards and generic Facebook sign-in cards are not equivalent to a playable video. Provider availability can change; a configured proxy is a candidate, not a success guarantee.
- New bounded last resort: `yt-dlp` is permitted for Facebook video links, and ONLY a successfully downloaded attachment (within guild file limits) counts as video preview success. If video extraction requires login or exceeds limits, return a clear status rather than invent media or request cookies.
- `action_required` (manual failure notice) never suppresses the user's native original embed by itself. The notice includes the original Facebook URL in a link button; **🔄** still retries, **❌** still reverts. Keep original preview if a reload cannot create a replacement. Multi-link messages with any action-required result keep native previews.
- Regression workflow `.github/workflows/asumi-embed.yml` runs `test_embed_resilience.py`, historical `test_release28.py` and `test_embed_audit.py`. No external video requests in automated tests. The actual Facebook sample must be re-tested in the Discord guild after Render deployment, including fallback file-size and embed-permission behavior.
- Status checklist: **code CI** is necessary but not proof of live Facebook permission/access. On the original screenshot's `/share/v/` link, verify provider selection, playback, preview controls, and Dashboard embed `reason/tier/proxy_domain`. If public extraction genuinely fails, original message and open-original action must remain available with honest diagnostics.
