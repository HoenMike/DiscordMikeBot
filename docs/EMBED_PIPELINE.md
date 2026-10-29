# Social Embed Pipeline

Tài liệu vận hành pipeline preview mạng xã hội của Asumi. **Chính sách Facebook hiện hành: 2026-10-26 — manual reversible proxy cycling, in-place edit.** Các mục ghi phiên bản cũ phía dưới là lịch sử, không còn là contract hiện hành.

## Thử nghiệm rich social embed (Components V2, opt-in, 2026-10-29)

- Nhánh thử nghiệm: `feat/asumi-social-native-v2-preview`. Không tự deploy/merge.
- Bật bằng environment variable `ASUMI_SOCIAL_NATIVE_V2_ENABLED=true` rồi khởi động lại bot. Mặc định **false** để không đổi production khi chưa smoke.
- Chỉ dựng `LayoutView → Container → Section/Thumbnail + MediaGallery + TextDisplay + ActionRow` khi API/yt-dlp đã cung cấp ảnh trực tiếp hợp lệ hoặc video **thực sự tải được** thành Discord attachment. Không nhận thumbnail thay video. Dữ liệu like/comment/share chỉ hiện khi provider trả giá trị thật.
- Facebook proxy **vẫn giữ nguyên** masked Markdown link ở `message.content` để Discord native-unfurl. Không tự đổi nguồn, không convert proxy URL thành MediaGallery. Nút Đổi nguồn tiếp tục edit tại chỗ, xoay vòng đến nguồn cũ.
- Legacy fallback: nếu không có media đủ chuẩn hoặc feature flag tắt, render cũ không đổi. Nếu Discord trả HTTP 4xx chắc chắn từ send V2 cho ảnh URL công khai, thử legacy embed; nếu upload file V2 bị từ chối, dừng và để Tier tiếp theo xử lý (không dùng lại attachment đã đóng). Send outcome không chắc chắn **không retry**.
- NSFW: chế độ block giữ nguyên; spoiler media chỉ vào gallery khi có attachment, container và gallery đều đánh dấu spoiler. Không truyền image NSFW từ CDN ngoài để tránh lộ.
- Quyền `Đổi nguồn / Reload` và `Ẩn` vẫn owner-only, dùng cùng callbacks và kiểm tra origin. Map origin khi restart phải đọc header từ V2 TextDisplay vì `message.content` rỗng.

**Smoke trên server thử nghiệm:** ảnh đơn, gallery, video attachment MP4, URL video chỉ có poster, spoiler/block, owner-only, reload/ẩn, xóa origin, restart + orphan cleanup, V2 HTTP 400, Facebook 2–3 proxy, desktop + mobile. Test/mock chưa chứng minh playback thật; chỉ xem là triển khai hoàn tất khi thử media trên Discord thật.
## Mục tiêu

Asumi ưu tiên native embed của Discord khi một proxy có thể tự unfurl video/media. Mọi preview do Asumi tạo đều có cùng bộ điều khiển owner-only **🔄 Reload** và **🗑️ Bỏ embed**. Với Facebook, **🔄 Đổi nguồn** là lựa chọn thủ công và có thể quay về nguồn đã dùng. Bot không đoán thành công qua REST/unfurl polling và không tự đổi nguồn.

## Pipeline chung

1. **Tier 0 — API fetcher**
   - Dùng API/oEmbed có cấu trúc khi nền tảng hỗ trợ.
   - Facebook hiện không có unauthenticated API fetcher phù hợp nên thường đi thẳng Tier 1.

2. **Tier 1 — Proxy**
   - Proxy được lấy từ `PROXY_DOMAINS` hoặc guild override.
   - Các candidate có thể được pre-validate bằng API/OpenGraph trước khi gửi.
   - Với Twitter/TikTok/Instagram/Reddit/... flow cũ vẫn có thể tự thử proxy tiếp theo nếu candidate gửi ra không dùng được.
   - Với **Facebook**, gửi đúng **nguồn đầu tiên trong cấu hình** có URL hợp lệ, rồi dừng. Metadata probe chỉ phục vụ kiểm tra NSFW best-effort, không dùng trạng thái video/player để tự thay proxy.
   - Người gửi bấm 🔄 Đổi nguồn để chuyển sang proxy kế tiếp. Hết danh sách sẽ quay về nguồn đầu tiên. Danh sách xoay vòng, kể cả nguồn đã thử; một proxy từng thất bại vẫn có thể chọn lại.

3. **Tier 2 — yt-dlp**
   - Twitter/X, TikTok, Instagram, Reddit và Twitch giữ cơ chế tự động hiện tại.
   - **Facebook không tự fallback xuống yt-dlp**, cả ở lần gửi đầu lẫn khi bấm đổi proxy. Không có file video riêng được gửi như một lựa chọn ẩn.

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
  - Facebook: nút **🔄 Đổi nguồn** chuyển proxy theo thứ tự, hết danh sách quay về nguồn đầu tiên và **edit chính message hiện tại**, không tạo message mới, không delete message cũ.
  - Provider khác: chạy lại pipeline cho đúng URL; preview hiện tại chỉ bị xóa sau khi replacement tạo thành công.
- **🗑️ Bỏ embed**: chỉ người gửi link gốc được dùng. Asumi unsuppress message gốc để Discord dựng native embed rồi dọn toàn bộ preview Asumi thuộc origin message.

Discord chỉ cho suppress/unsuppress ở cấp **message**, không theo từng URL. Vì vậy với message chứa nhiều social URL, Bỏ embed revert toàn bộ origin message thay vì chỉ xóa một preview; cách này tránh native preview và Asumi preview bị trùng nhau.

Cả interaction layer và server-side handler đều kiểm tra lại `author_id`, origin message và original URL trước khi thay đổi trạng thái.

## Facebook proxy roll hiện hành (2026-10-26)

- Buttons: **🔄 Đổi nguồn**, **❌ Ẩn**; chỉ người gửi link gốc được thao tác. Xác thực lại origin message/author/original URL trước khi edit.
- Trạng thái `current_domain` trong control + cache server `_facebook_current_domain[(origin_id, url)]`; không dùng `tried_domains` để ngăn quay lại. Dữ liệu control cũ có thể suy ra domain từ content hiện tại.
- Danh sách proxy dựa trên guild override hoặc mặc định; loại domain sai định dạng và trùng. Chọn proxy tiếp theo theo modulo, tự quay về proxy đầu tiên khi hết danh sách.
- Mỗi lần roll gọi **`current_preview.edit(content=..., view=...)`**. Không gọi send, delete, Discord unfurl verifier hoặc yt-dlp khi chọn nguồn. Cùng `preview_message_id`, vị trí chat không đổi.
- Nếu Discord từ chối edit: không cập nhật nguồn hiện tại, giữ message và nút cũ. Với lỗi PATCH không rõ kết quả, không tự retry/rollback gây trùng hoặc ghi đè.
- Preflight OpenGraph chỉ hỗ trợ NSFW; login-card, ảnh thumbnail hoặc timeout không tự động quyết định chuyển nguồn. Kết quả thực tế người dùng nhìn thấy phải được kiểm tra trên Discord client.
- **❌ Ẩn** vẫn khôi phục native embed và cleanup các Asumi preview; xóa message gốc vẫn cleanup như trước.

## Vì sao không server-side auto-roll Facebook

Discord client có thể render/unfurl khác thời điểm với polling của bot. Một server-side classifier có thể nhìn thấy timeout/generic card trong khi client vừa dựng được video đúng. Nếu bot tự xóa message proxy và thay candidate khác, nó có thể phá một preview đang hoạt động.

v2.8.3 vì vậy dùng quy tắc đơn giản:

- **send compact masked proxy link**;
- **không auto-roll sau send**;
- **user quyết định khi nào cần proxy khác**.

Các helper verify unfurl vẫn còn cho flow của nền tảng khác và regression coverage, nhưng không quyết định rotation sau khi Facebook proxy đã được gửi.

## State và regression (hiện hành)

- `_origin_to_preview_map` vẫn map cùng một message qua tất cả lần roll; `_facebook_current_domain` lưu nguồn hiện tại, xóa khi origin bị xóa/revert. Không còn "hết nguồn" vĩnh viễn hay cooldown tự động.
- Test: gửi lần đầu đúng 1 preview dù metadata báo không có player; không gọi `_verify_proxy_unfurl`, `_discard_preview` hoặc `yt-dlp` cho Facebook; nút Đổi nguồn quay vòng tới cả nguồn cũ; cùng preview ID khi edit; lỗi edit không xóa; quyền author-only; NSFW spoiler/block; các nguồn ngoài Facebook giữ behavior cũ.
- Discord có thể không dựng lại unfurl ngay khi edit link. Điều này cần smoke thực tế với 2–3 proxy Facebook khác nhau, kể cả khi thumbnail đã tải, cùng URL reel/share, desktop/mobile. Không diễn giải test mock là chứng minh phát video live.

## Historical notes (superseded by 2026-10-26 Facebook policy)

## v3.10.1 — Incident Facebook shared video & acceptance

- **Root cause from code review:** `build_proxy_url()` rewrote a Facebook `/share/v/{token}` video share path into `/share/r/{token}` Reel path, silently changing the lookup type. Preserve the literal path and query. Numeric `/reel/{id}` paths still normalize to `/watch?v={id}` as before.
- For Facebook **video** paths, OG validation accepts only a real video/player tag; image-only cards and generic Facebook sign-in cards are not equivalent to a playable video. Provider availability can change; a configured proxy is a candidate, not a success guarantee.
- New bounded last resort: `yt-dlp` is permitted for Facebook video links, and ONLY a successfully downloaded attachment (within guild file limits) counts as video preview success. If video extraction requires login or exceeds limits, return a clear status rather than invent media or request cookies.
- `action_required` (manual failure notice) never suppresses the user's native original embed by itself. The notice includes the original Facebook URL in a link button; **🔄** still retries, **❌** still reverts. Keep original preview if a reload cannot create a replacement. Multi-link messages with any action-required result keep native previews.
- Regression workflow `.github/workflows/asumi-embed.yml` runs `test_embed_resilience.py`, historical `test_release28.py` and `test_embed_audit.py`. No external video requests in automated tests. The actual Facebook sample must be re-tested in the Discord guild after Render deployment, including fallback file-size and embed-permission behavior.
- Status checklist: **code CI** is necessary but not proof of live Facebook permission/access. On the original screenshot's `/share/v/` link, verify provider selection, playback, preview controls, and Dashboard embed `reason/tier/proxy_domain`. If public extraction genuinely fails, original message and open-original action must remain available with honest diagnostics.


## v3.14.5 — Facebook Reels/Share verification (2026-10-17)

Case phát hiện: Facebook `/share/v/{token}/` phát được khi người xem đang đăng nhập trong trình duyệt nhưng bot nhận link có thể chỉ thấy thẻ `Log in or sign up to view`. Kết quả Facebook đang có thể không công khai với bot/Discord; tuyệt đối không suy luận thành công chỉ từ ảnh hoặc việc `send()` trả về message.

- **Đường đi tự động:** validate proxy bằng Discord crawler User-Agent thật (thời gian chờ Facebook cold preview có giới hạn), gửi candidate, rồi poll Discord message đã render. Link Facebook video yêu cầu `embed.video.url` hoặc `embed.type == "video"`; ảnh/poster/text card là thất bại. Chỉ suppress embed nguyên bản khi có player hoặc file video thực sự được gửi.
- **Nếu candidate lỗi:** xóa preview thử (không để rác), thử host khác, và chỉ sau đó thử yt-dlp video-only có giới hạn kích thước. Nếu cleanup không chắc chắn thì dừng, không gửi trùng nhiều preview.
- **Reload thủ công:** phải xác nhận preview mới rồi mới thay preview cũ. Candidate timeout/login-card chỉ tính là thử trong lượt hiện tại, không vĩnh viễn đánh dấu `tried`; sau 30 giây có thể thử lại. Khi đã thực sự đi hết proxy hợp lệ, reset một vòng mới sau cooldown.
- **UX:** Facebook có nút ghi rõ `🔄 Thử lại` / `❌ Ẩn`; không khóa nút retry vĩnh viễn sau lỗi. Khi không phát được video, giữ link Facebook gốc và giải thích ngắn gọn. Không yêu cầu cookie/tài khoản người dùng.
- **Kiểm thử:** unit tests cho Reel chỉ có thumbnail, login card, candidate đầu sai nhưng candidate thứ hai phát được, manual reload lỗi giữ preview cũ. CI kiểm thử API/tình huống giả lập; chưa thay thế smoke test trên Discord thật với link cụ thể.
- **Giới hạn khách quan:** không thể phát video private/geo-locked/đòi đăng nhập nếu Facebook hoặc proxy không cấp luồng công khai, ngay cả khi người dùng tự xem được trên browser đăng nhập. Không tự nhận đã xác minh live khi CI mới chạy.


## v3.14.6 — Facebook short Reel URL canonicalization

- The screenshot `https://www.facebook.com/share/r/1KfknmPddc/` can render a Facebook login card in Discord even while an authenticated browser can open it.
- To improve publicly accessible Reels, the embed path first makes one **best-effort, bounded HTTP probe** of `/share/r/` and `/share/v/` URLs. It accepts a canonical URL only from explicitly allowed HTTPS Facebook hostnames, and only numeric `/reel/{id}`, `/videos/{id}` or `/watch?v={id}` forms. The probe uses no user cookies, follows at most four redirects and never follows external hosts.
- When a canonical video is found, try it with the current validated proxy chain and video-only yt-dlp fallback. The original share link remains the source of truth for interaction ownership and original-message cleanup. If no canonical route is available, the original route remains unchanged.
- When video extraction is denied or unplayable, keep the original Discord message and display **one short, owner-controlled failure line**, not another large login-card link/button; Retry + Hide remain. The original Facebook URL is already clickable in the source message.
- Regression tests verify canonical redirect, `og:url`, login redirect rejection, foreign/HTTP URL rejection, backend candidate selection, and compact fallback UX. Live Discord playback still requires an actually public Facebook video (and post-deploy smoke is mandatory).
