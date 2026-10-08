# Changelog

Các thay đổi của bot Discord **Asumi** được ghi tại đây.

Tài liệu dựa trên [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) và dùng
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) (`Major.Minor.BugFix`).

---

## [3.7.4] - 2026-10-08 — *Brave Search UX Polish*

### Changed
- Replace long plain-text Brave search results with a concise, answer-first Discord Embed: brief grounded synthesis plus up to three clickable original sources.
- Clean HTML tags, Markdown injection/mentions and numeric citation placeholders from provider snippets before display.
- For Vietnamese fuel prices, use a more targeted *single* Brave query with local date/RON95/E10/official seller context; prefer direct publisher domains in presentation and demote aggregators/chart sites.
- Grounded summarizer must avoid claiming a live price unless snippets actually contain an identifiable value, unit and relevant timestamp.
- Source cap is controlled by `ASUMI_WEB_SEARCH_DISPLAY_SOURCES` in `core/constants.py`, not an environment flag. Existing 500/month request cap and safe provider boundaries unchanged.
- CI includes UI, sanitization, source prioritization and new fuel-query regression. Live data correctness still requires inspecting source publication dates.

## [3.7.3] - 2026-10-08 — *Code-owned Asumi Search Configuration*

### Changed
- Move **all Asumi runtime feature switches, model choices, quotas, timeouts, session/cache/context settings** into `core/constants.py`. Render Environment is reserved for external credentials and deployment identifiers.
- Brave Search automatically becomes available when `BRAVE_SEARCH_API_KEY` is supplied. Durable Turso quota database is required before any chargeable call; monthly cap stays 500, hard ceiling 900.
- Conservative local routing for clearly current public gas/oil/gold/FX price questions (e.g. `@Asumi giá xăng hôm nay như nào`) works even if Clef is unavailable.
- If Brave key is absent, the bot says the key is missing rather than incorrectly claiming the search feature is not integrated.
- Explicit/native Discord History Search is code-enabled, still constrained by bot token and requester/bot channel permissions. Vectorize semantic search remains code-disabled pending live permission/cost acceptance.
- `.env.example` now lists only external credentials/connection identifiers. All old `ASUMI_*_ENABLED`/model/quota env values are deliberately ignored; change policy in source and redeploy.

### Safety
- No private Discord history may be forwarded to Brave, public source links preserved, and no passive guild indexing.
- Production acceptance still requires real Discord guild Search API/ACL and Brave provider billing smoke tests.

## [3.7.2] - 2026-10-08 — *T22.4b Search Follow-up & Observability*

### Added
- Allow explicitly saying `@Asumi tìm tiếp trên web giá Honda SH160i hôm nay`. Only the user's current public query reaches Brave; provider quota/private-reference guards continue to apply.
- Reply to Search results with bounded conversational context and a stronger no-fabricated-evidence instruction; do not automatically rerun a tool on vague follow-up.
- Display Discord History source channel when known and the requester has permission; original Jump links remain.
- Dashboard activity rows show Brave status/results/cache/quota and Discord History status/results/API calls/permission filtering; no prompt or private search content.
- Evict expired Brave cache entries on lookup; fail safely for explicit web queries referencing private Discord context.

### Remaining
- Provider keys/feature flags and real-server permissions smoke tests are still required. Multi-source chained search without exposing private history to a public provider is deferred to T22.5.

## [3.7.1] - 2026-10-08 — *T22.4a Temporal Discord History Search*

### Added
- `@Asumi tìm tin nhắn đầu tiên của @user`, `tìm 5 tin nhắn đầu tiên`, or `tìm tin nhắn gần nhất` without requiring a content keyword.
- `@Asumi lần đầu @user nhắc tới Minecraft là khi nào?` finds chronologically earliest indexed matches for a given topic.
- Timestamp ascending/descending Discord Search, original Jump links, author filtering, ACL checks and bounded live verification.
- Explicit wording "earliest/latest found" rather than claiming the absolute first message in server history.

### Safety / rollout
- Requires existing `ASUMI_DISCORD_HISTORY_ENABLED=true` and real bot-token/permissions tests; disabled by default.
- Limit five results, at most three API calls; no passive indexing.
- T22.4b multi-source follow-up, cache/dashboard improvements remain pending.

## [3.7.0] - 2026-10-08 — *T22.3 Intelligent Source Routing*

### Added
- Optional Clef source selection among public Brave web, historical Discord messages, and user-owned Archive.
- Typed Python safety gate: provider must be enabled; private Discord references cannot become automatic public web queries.
- Clear current/public-info questions can trigger Brave automatically; clear historical messages use Discord Search, explicitly saved content uses Archive.
- Optional Gemini short grounded synthesis for Clef-selected Brave results, showing original source URLs and falling back to source list on AI timeout.

### Safety
- `ASUMI_AUTO_SEARCH_ENABLED=false` by default; no auto Brave/Discord requests until manually enabled.
- Ordinary conversation/reply follow-up and deterministic commands still take priority; no recursive tool loop.
- Existing per-provider quota, history permissions, time budget and privacy limits still apply.

## [3.6.0] - 2026-10-08 — *T22.2 Discord History Search*

### Added
- Explicit historical Discord search: `@Asumi tìm xem đầu năm @Theo có nhắn gì về mua xe không?` (no prior Archive save required).
- Native guild Search API through bot token, bounded synonyms, author ID/time window, up to 5 original results with Discord Jump links.
- Requester-and-bot channel permission checks, private thread/unknown channel fail closed; no passive indexing.
- 202 indexing / 429 / timeout handling, 20s user cooldown, request caps and privacy-safe Dashboard metadata.
- Search regression GitHub Actions CI added for Brave + History adapters.

### Activation
- `ASUMI_DISCORD_HISTORY_ENABLED=false` by default pending real-server permission and bot-token API validation.
- Clef automatic source selection still belongs to T22.3.

## [3.5.0] - 2026-10-08 — *T22.1 Brave Web Search*

### Added
- Explicit `@Asumi tìm trên web ...` through Brave Search API (no Clef auto-search yet).
- Real source URLs and snippets, safe mention escaping, disabled without admin-provided key + flag.
- Durable monthly Brave request reservations in existing Turso/SQLite, default max 500 and absolute app cap 900; fail closed when quota DB is unavailable.
- Per-user cooldown, bounded result count/timeout, short-lived cache, no API retry or paid provider fallback.
- Privacy: reject Discord mention/message URLs in outbound queries; do not send replied/private context or Archive to Brave.
- Dashboard metadata captures status/provider/latency/cache/quota without storing search content.

## [3.4.1] - 2026-10-08 — *Conversational Timeout Budget*

### Fixed
- Replaced per-fallback full timeouts with a hard total conversational AI budget.
- Defaults: 4s per model, 8s total AI budget, maximum 2 attempts.
- Chat fallback order now prefers `gemini-3.1-flash-lite` before heavier summary models.
- Later attempts only receive the remaining request budget; exhausted budget stops immediately.
- Error telemetry now records `ai_ms`, models tried, attempts, budget and last provider error type.
- Dashboard labels conversational timeout-budget failures explicitly.

## [3.4.0] - 2026-10-08 — *Intelligence Polish*

### Observability
- Asumi AI activity telemetry now records Archive save/search/forget, lexical vs semantic-hybrid/fallback mode, semantic latency and match counts.
- Admin Dashboard shows Archive mode + Vectorize latency inline; semantic fallback is highlighted without exposing query/source content.
- Clef error/low-confidence fallback is visible in the activity summary instead of requiring Render logs.

### Reliability
- Semantic query returns typed status/latency reports for `ok`, `no_match`, `permission_error`, `unavailable`, and `error` paths.
- Archive semantic calls have a configurable concurrency guard (default 3).
- First Vectorize index initialization is serialized to avoid concurrent auto-create races.
- Added concurrency/load smoke coverage and regression coverage for semantic-to-lexical fallback metrics.

## [3.3.1] - 2026-10-08 — *Archive Semantic Retrieval*

### Added
- Optional multilingual semantic retrieval for Asumi Archive using Workers AI `@cf/baai/bge-m3` + Cloudflare Vectorize.
- Hybrid result ranking: semantic matches first, lexical matches fill remaining slots, duplicates removed, maximum 5 Discord results.
- Per-user Vectorize namespaces plus a second owner check against canonical Turso/SQLite rows before anything is shown.
- Best-effort background upsert on Save and vector cleanup after Forget.

### Reliability / privacy
- Semantic mode is OFF by default and never blocks Archive Core.
- A separate `CLOUDFLARE_VECTORIZE_TOKEN` is supported so the existing Workers AI/Clef credential does not need to be replaced.
- Missing/invalid Vectorize permission or API failure falls back to lexical search; no paid provider fallback is introduced.
- Vectorize is derived state only: canonical Archive content remains in `core.db` (Turso/SQLite).

## [3.3.0] - 2026-10-08 — *Asumi Archive Core*

### Added
- Explicit **Save / Search / Forget** long-term memory for @Asumi.
- Reply a message/link/image then say @Asumi nhớ cái này to save source metadata and Jump to Message.
- Search user-owned memory with natural phrases such as @Asumi tìm lại meme mèo Khai.
- Delete by stable Archive ID with @Asumi quên #12.
- Archive actions are deterministic tools and do not spend Clef/Gemini quota.

### Privacy & storage
- No passive logging: a bare save request without a replied source, direct link, or attachment is rejected.
- Archive rows are scoped to owner_user_id; search/delete cannot cross users.
- Existing core.db (Turso Cloud with SQLite fallback) is the canonical store to avoid a second D1 source of truth.
- Media binary is not copied in 3.3.0; only source URL/attachment/embed metadata is stored.
- Semantic Vectorize/R2 enhancement remains a follow-up after live validation of the core flow.

## [3.2.1] - 2026-10-07 — *Tarot finalizing UX hotfix*

### Fixed
- Khi user đã lật hết bài nhưng AI còn đang chạy, trạng thái **ĐANG LUẬN GIẢI — CHƯA XONG** giờ nằm ngay trên Reading Board thay vì ở embed thứ hai phía dưới ảnh.
- Loading state nói rõ phần lật bài đã hoàn tất, Asumi vẫn đang viết luận giải, user không cần bấm gì thêm và message sẽ tự cập nhật.
- Daily / Single / Yes-No một lá dùng layout final gọn một embed: **HOÀN TẤT → lá bài → luận giải → ảnh**, giảm scroll và bỏ phần card summary lặp.
- Yes/No vẫn giữ verdict trong layout compact; multi-card spread giữ layout chi tiết hiện tại.

## [3.2.0] - 2026-10-07 — *Context + Lens*

### Added
- **Reply context**: tag Asumi while replying to a message and Asumi receives that message as bounded context.
- **Selective recent context**: recent channel messages are fetched only for referential requests such as `cái này`, `cái trước`, `phía trên`, `vừa rồi`.
- **Image Lens**: PNG/JPEG/WEBP can come from the current message or the replied message and are sent as multimodal input to Gemini 3.5 Flash-Lite.
- **Image follow-up**: live sessions keep at most two bounded image snapshots in memory so a reply like `vậy sửa chỗ nào?` can still refer to the previous screenshot.
- **Link Lens**: URLs are collected from current/reply/recent context; Gemini URL Context is enabled when URLs are present, with Discord embed metadata as fallback context.

### Reliability
- Replies to the latest live-session Asumi answer are conversational continuations and do **not** run Clef/tool routing again.
- Natural-language Tarot/Summary tool calls capture a bounded set of bot output message IDs, so replies to tool output (including multi-message results) continue the same session.
- Tool follow-up reads the replied bot message at reply time, allowing edited Tarot Reading Boards to provide current embed/image context.
- Replies to older Asumi messages, replies from another user, and expired sessions do not inherit the original user's session.
- Image-only mentions route to vision chat instead of Help.
- Context/image counts and context-build latency are included in privacy-safe Asumi dashboard telemetry.

### Privacy & bounds
- Default recent history bound: 8 messages / 7000 context characters.
- Default image bound: 2 images / 5 MiB each.
- Image snapshots are in-memory only for the short live session; no DB/R2 persistence.
- Expired sessions are actively pruned every 5 minutes so retained image bytes are released from RAM after TTL.
- Audio/voice transcription remains out of scope.

## [3.1.2] - 2026-10-07 — *Dashboard AI telemetry*

### Added
- **Asumi AI** filter trong Admin Dashboard → Log Tương Tác.
- Bảng activity hiển thị tổng latency hiện có cùng model và AI/Clef timing ngắn gọn cho request conversational.
- Modal Chi tiết hiển thị toàn bộ timing metadata: route, Clef, AI, Discord send, total, model, attempts, source và intent.

### Privacy
- Conversational telemetry không lưu nguyên prompt/response; chỉ giữ metadata hiệu năng, user/server/channel và số ký tự input/output.

## [3.1.1] - 2026-10-07 — *Conversational latency hotfix*

### Changed
- Conversational chat mặc định chuyển sang **Gemini 3.5 Flash-Lite** để ưu tiên RPD/throughput; 3.8 Flash chỉ còn trong fallback chain.
- Greeting/test rõ ràng như `hello`, `hi`, `ping` bỏ qua Clef để tránh một network round-trip không cần thiết.
- Timeout conversational mặc định giảm còn **6 giây/model** và tối đa **2 attempts**.

### Observability
- Render log có `[Asumi Timing]` với `route_ms`, `clef_ms`, `ai_ms`, `send_ms`, `total_ms`, model và số attempt.
- Lỗi model ghi luôn latency trước khi timeout/fallback để xác định bottleneck.

## [3.1.0] - 2026-10-07 — *Conversational Core*

### Added
- **@Asumi conversational entrypoint**: tag bot rồi nói tự nhiên; câu không khớp command cũ sẽ đi vào assistant.
- **Reply continuation**: reply response conversational gần nhất để tiếp tục bounded session mà không cần tag lại.
- **Typed tool routing**: natural language route về Help, Tarot launcher/Daily và Summary/Catch-up bằng chính command engine hiện có.
- **Optional Clef-flash router**: Workers AI decision router đã có adapter nhưng mặc định tắt cho tới khi cấu hình Cloudflare credentials.

### Reliability
- Valid slash / `.m` / mention commands luôn được ưu tiên trước conversational AI.
- Normal unmentioned chat không kích hoạt assistant.
- Session chỉ giữ vài turn gần nhất, mặc định TTL 20 phút; không tạo transcript database.
- Command bridge dùng shallow-copy message nên không mutate gateway event và vẫn giữ command checks/cooldowns.
- Clef thiếu credentials, timeout hoặc confidence thấp sẽ fail safe về local router; deterministic commands vẫn hoạt động.
- Daily mention flow bỏ filler tự nhiên như `đi`, `nha`, `cho tôi` thay vì coi đó là câu hỏi Tarot.
- Audio/voice transcription bị loại khỏi roadmap Asumi 3.x; image input vẫn là requirement của 3.2.

## [3.0.1] - 2026-10-05 — *Tarot renderer title hotfix*

### Fixed
- Reading Board không còn hard-cut spread title ở 44 ký tự rồi thêm `...`.
- Title dài giữ nguyên đầy đủ và tự giảm font vừa phải; nếu vẫn chưa đủ chỗ sẽ wrap tối đa hai dòng.
- Fix áp dụng cho Reading Board chính, visual fallback và Clarifier Board.
- Thêm regression cho **Mind - Body - Spirit (Tâm Trí - Thể Chất - Trực Giác)** và Smart Custom Spread title dài.

## [3.0.0] - 2026-10-05 — *Asumi 3.0 — Tarot-first UX*

### Changed
- **Hai primary path rõ ràng trong `/tarot` / `.m tarot`**: **✏️ Nhập câu hỏi** cho smart recommendation hoặc **☀️ Daily hôm nay** để vào Daily ngay.
- **One-click recommendation**: sau khi nhập câu hỏi, **✨ Trải theo đề xuất** chấp nhận spread Asumi gợi ý và bắt đầu quẻ trong cùng một thao tác.
- **Manual controls thành advanced options**: dropdown tự chọn spread và Reader Style được đưa xuống dưới, không còn khiến người mới nghĩ rằng bắt buộc phải biết spread trước.
- **Daily không cần câu hỏi**: quick button trong launcher, `/tarot spread:Daily Card` và `.m tarot daily` đều được giữ.
- **Slash/prefix parity**: `.m tarot <câu hỏi>` vẫn hiểu toàn bộ text là câu hỏi, mở launcher và đưa recommendation giống flow slash.

### Reliability
- Nếu one-click Daily/recommendation bị Daily cooldown hoặc anti-spam cooldown chặn, selection state được rollback để button đang hiển thị vẫn dùng lại được.
- Giữ nguyên Tarot 2.1 runtime: Smart Custom Spread, Reading Board, 3 follow-up, Why, Clarifier 1/1, Journey và Recap.
- Help/README/docs được cập nhật theo flow thực tế.

### Versioning
- **Tarot 2.x** tiếp tục là tên generation của subsystem Tarot.
- **Asumi 3.0.0** là major version của toàn bot, phản ánh việc Tarot 2.x trở thành một trải nghiệm lớn và launcher được tái thiết kế quanh flow đó.

## [2.10.0] - 2026-10-05 — *Tarot 2.1*

### Added
- **Multi-turn Reading Session**: tối đa 3 follow-up có context liên tục; clarifier đã giao thành công được giữ làm context nhưng vẫn 1/1.
- **🔍 Vì sao?**: giải thích evidence từ lá/vị trí đang hiển thị, owner-only và không hiển thị suy luận nội bộ.
- **Smart Custom Spread**: AI chỉ tạo schema 3–7 vị trí; deck engine tự rút lá, schema lỗi fallback spread chuẩn.
- **Tarot Journey**: `/tarot_journey` và `.m tarot journey` tổng hợp 30 ngày gồm suit mix, Major ratio, lá lặp/lá ngược lặp, topic progression và spread dùng nhiều.
- **Journey Card**: visual summary 1400×900, framing rõ đây là thống kê tự phản chiếu.
- **📌 Recap Card**: owner-only, portrait save/share-friendly với hero/key card, headline, một takeaway, spread và ngày; không gọi AI thêm.

### Reliability & UX
- Follow-up chỉ tiêu lượt sau delivery thành công; generation/send failure giữ nguyên capacity.
- Session hết hạn sẽ khóa follow-up, clarifier, Why và Recap.
- Custom schema validator chặn count ngoài 3–7, duplicate, card/orientation do model cung cấp và private third-party framing.
- Suit percentages của Journey luôn được phân bổ nhất quán về tổng 100% khi có Minor Arcana.
- Journey chỉ đọc `tarot_history`; `/tarot_forget` tiếp tục xóa nguồn dữ liệu của Journey.
- T20.1–T20.9 được đồng bộ trong handoff/master/system docs để agent sau tiếp tục bảo trì trực tiếp từ repo.

## [2.9.0] - 2026-10-04 — *Tarot 2.0*

### Added
- **Clarifier 1/1**: sau quẻ hoàn tất, chủ quẻ có thể chọn một vị trí để rút đúng một lá bổ sung; target do Asumi gợi ý được đưa lên đầu picker.
- **Clarifier Board**: giữ toàn bộ quẻ gốc, đánh dấu **TARGET** và hiển thị quan hệ **TARGET → CLARIFIER** thay vì thay/reroll lá cũ.
- **Bounded clarifier interpretation**: AI chỉ giải quan hệ giữa vị trí gốc và lá bổ sung, nói rõ phần sáng tỏ, tác động, bước thực tế và uncertainty.
- **Persistence riêng**: Clarifier đã giao thành công được lưu riêng để không mutate tarot_history.

### Tarot 2.0 release boundary
- T20.1 — Reading Engine 2.0: structured reading, natural Asumi prompt, card connections, key card, uncertainty.
- T20.2 — Question-first Launcher: đề xuất spread theo câu hỏi, explicit accept/manual override, repeated-question awareness.
- T20.3 — Live Reading Session: one-message flow, progress, micro reveal, AI-ready/finalizing states, compact controls.
- T20.4 — Reading Board 2.0: responsive 1/3/5/10-card layouts, dynamic 4/6/7 layouts, REV/Major/KEY/NEW/TARGET states và visual fallback.
- T20.5 — Clarifier: target picker, deterministic one-card draw, board, contextual interpretation, 1/1 limit và persistence.

### Reliability
- Clarifier không lấy lại bất kỳ lá nào của spread gốc và không thay đổi order/chiều/kết quả quẻ đã hoàn tất.
- Retry Clarifier được bind vào đúng spread gốc để lỗi delivery không âm thầm đổi sang một lá khác.
- Lượt Clarifier chỉ bị khóa sau khi Discord nhận được output; lỗi render/AI/delivery không làm mất quẻ gốc hoặc tiêu lượt.
- Output AI được giới hạn để nằm an toàn trong Discord embed; nếu attachment lỗi, bot thử gửi bản text-only trước khi coi delivery thất bại.
- Giữ nguyên toàn bộ social-embed behavior của v2.8.5 và các hotfix icon-only/neutral remove button trên main.

## [2.8.5] - 2026-10-04 — *Universal Embed Controls*

### Added
- **Hai action cho toàn bộ social preview**: mọi preview Asumi từ API, proxy và yt-dlp đều có **🔄 Reload** và **🗑️ Bỏ embed**.
- **Owner-only**: chỉ người đã gửi link gốc được thao tác hai nút; user khác chỉ nhận cảnh báo ephemeral.
- **Native revert**: **Bỏ embed** bật lại native embed trên message gốc (`suppress=False`) rồi dọn các preview Asumi của message đó.
- **Reload an toàn**: provider ngoài Facebook chạy lại pipeline cho đúng URL và chỉ thay preview cũ khi replacement thành công; thất bại giữ nguyên preview hiện tại.

### Preserved
- Facebook **Reload** tiếp tục mang semantics manual proxy roll của v2.8.3/v2.8.4: thử proxy kế tiếp, không tự nhảy yt-dlp.
- Khi Facebook hết proxy, Reload bị khóa nhưng **Bỏ embed** vẫn dùng được để quay về native Discord embed.
- NSFW guards, deletion lifecycle và automatic yt-dlp fallback của các provider được hỗ trợ vẫn giữ nguyên.

## [2.8.4] - 2026-10-04 — *Compact Facebook Proxy Hyperlink*

### Fixed
- **Dòng preview gọn hơn**: URL proxy dài không còn hiện thành một dòng riêng. Asumi hiển thị domain như **facebed.seria.moe** và gắn URL proxy trực tiếp vào chữ đó bằng masked link.
- **Giữ link preview**: masked link dùng dạng `[domain](url)`, không dùng `[domain](<url>)` vì angle brackets sẽ suppress preview.
- **Spoiler đúng cú pháp**: spoiler bọc toàn bộ masked link, không chèn `||` vào URL target.
- **Áp dụng nhất quán**: cả preview Facebook ban đầu và preview mới sau khi bấm **🔄 Proxy khác** đều dùng compact link.

### Unchanged
- Chỉ người gửi link gốc được bấm **Proxy khác**.
- Facebook vẫn roll proxy thủ công, không auto-roll và không dùng yt-dlp fallback.
- Proxy cũ chỉ bị dọn sau khi proxy mới gửi thành công.

## [2.8.3] - 2026-10-04 — *Facebook Raw Proxy Embed & Manual Proxy Roll*

### Fixed
- **Khôi phục đúng cơ chế Discord unfurl**: Facebook proxy URL được gửi dưới dạng **raw URL trên một dòng riêng**. Masked markdown link không còn được dùng cho link tạo embed, vì Discord cần nhìn thấy URL trực tiếp để dựng native embed/video.
- **Fallback đúng nghĩa là đổi proxy**: nút giờ là **🔄 Proxy khác**; bấm nút sẽ chuyển sang proxy Facebook kế tiếp trong cấu hình thay vì chạy yt-dlp.
- **Không auto-roll sau khi đã gửi proxy**: server-side verify không còn tự quyết định thay proxy Facebook vừa gửi. Nếu preview hiện tại không ổn, chính người gửi link mới bấm đổi proxy.
- **Không yt-dlp cho Facebook**: Facebook được loại khỏi yt-dlp fallback path. Khi đã thử hết proxy, Asumi chỉ báo hết proxy và giữ preview hiện tại.
- **Replace an toàn**: proxy cũ chỉ bị xóa sau khi message chứa raw URL của proxy mới đã gửi thành công.

### Changed
- Nút vẫn owner-only: chỉ người gửi link gốc có thể đổi proxy; user khác nhận phản hồi ephemeral.
- Trạng thái proxy đã thử được giữ theo `(origin_message_id, URL)`, nên mỗi lần bấm tiếp tục từ proxy kế tiếp và không quay lại proxy cũ.
- Twitter/TikTok/Instagram/Reddit/Twitch vẫn giữ automatic yt-dlp fallback hiện tại.
- Cập nhật README, docs pipeline và regression tests cho raw-unfurl + proxy-roll flow.

## [2.8.2] - 2026-10-04 — *Native Facebook Fallback Button*

### Fixed
- **Fallback hoạt động trực tiếp trong Discord**: bỏ masked hyperlink của v2.8.1 và chuyển sang nút Discord native **↪️ Fallback**, không còn phụ thuộc public URL, browser hay JavaScript.
- **Owner-only interaction**: chỉ đúng Discord user đã gửi link gốc được kích hoạt fallback; người khác bấm sẽ nhận thông báo ephemeral.
- **State an toàn**: nút disable ngay khi chạy; nếu yt-dlp thất bại thì nút được bật lại và preview hiện tại vẫn giữ. Chỉ cleanup preview cũ sau khi replacement gửi thành công.
- **Per-URL cleanup**: manual fallback track preview theo `(origin_message_id, URL)`, tránh xóa nhầm khi một message có nhiều link Facebook/social.

### Changed
- Giữ nguyên cơ chế chống false fallback của v2.8.1: Facebook không auto yt-dlp, generic/login card ở poll sớm tiếp tục được chờ hết grace window.
- Xóa `features/embed/manual_fallback.py`, web fallback routes và cấu hình `ASUMI_PUBLIC_URL` / `PUBLIC_BASE_URL`.
- Cập nhật README, tài liệu pipeline và regression tests cho button flow.

## [2.8.1] - 2026-10-04 — *Facebook Manual Fallback Link*

### Fixed
- **Không auto-fallback Facebook khi Discord unfurl chậm**: generic/login card ở poll sớm không còn fail-fast; Asumi chờ hết grace window để Discord có cơ hội nâng cấp thành preview/video thật. Nếu vẫn chỉ là timeout, bot giữ preview hiện tại thay vì xóa nó rồi tự thay bằng yt-dlp.
- **Không phá preview tốt bằng fallback kém hơn**: Facebook chỉ dùng yt-dlp khi người dùng chủ động kích hoạt; Twitter/TikTok/Instagram/Reddit/Twitch vẫn giữ cơ chế fallback tự động hiện có.
- **Cleanup an toàn**: preview/prompt cũ chỉ bị xóa sau khi manual fallback đã gửi preview mới thành công. Nếu yt-dlp lỗi, preview hiện tại vẫn còn nguyên.

### Added
- **Hyperlink `[fallback]` nhỏ gọn trên preview Facebook**: thay cho button Discord. Link ký bằng `FLASK_SECRET_KEY`, hết hạn sau 15 phút.
- **Route manual fallback chống prefetch**: GET chỉ hiển thị trang trung gian; JavaScript mới POST yêu cầu chạy fallback, tránh crawler hoặc Discord link preview vô tình kích hoạt tác vụ.
- **Public URL config**: hỗ trợ `ASUMI_PUBLIC_URL`; trên Render tự dùng `RENDER_EXTERNAL_URL`.
- **Regression tests**: cover race condition `unfurl_timeout`, trạng thái `action_required`, signed token và bảo đảm các nền tảng ngoài Facebook vẫn auto-fallback.

## [2.8.0] - 2026-09-25 — *Asumi - Xác minh bản xem trước & Thống nhất phong cách Tarot*

### Tên gọi Asumi
- Đổi tên hiển thị hiện tại trong Discord, website, phần trợ giúp, Cabin và thông tin phiên bản thành Asumi. Tarot vẫn nhận tên gọi cũ trong câu hỏi; tên repository, cơ sở dữ liệu và lịch sử phát hành được giữ nguyên.

### Bản xem trước mạng xã hội có xác minh
- Loại thẻ đăng nhập Facebook chung chung dù có ảnh OG. Sau khi gửi liên kết proxy, bot chờ và kiểm tra bản xem trước trên Discord trong thời gian giới hạn; nếu không dùng được, bot xóa tin thử, chuyển sang proxy tiếp theo rồi dùng phương án dự phòng khi cần.
- Chỉ ẩn embed gốc và ghi nhận thành công khi đã có bản thay thế dùng được. Thông báo ngắn gọn khi phải dùng phương án dự phòng hoặc khi không thể tạo bản xem trước.

### Một Asumi với nhiều phong cách Tarot
- Asumi là nhân vật Tarot duy nhất, có bốn phong cách: Tự động, Tĩnh, Dịu và Tinh quái. Tự động là mặc định. Prompt ngắn hơn, bám câu hỏi và tránh câu nói lặp lại; quy tắc an toàn và bộ phân tích JSON có cấu trúc vẫn được giữ. ID phong cách cũ, lịch sử và đánh giá vẫn tương thích.

---

## [2.7.6] - 2026-09-17 — *Modal Limit Clamp & Cooldown Message Restoration*

### Fixed
- **Lỗi Mở Modal Đặt Câu Hỏi Tarot (50035 Invalid Form Body)**: Nhấn nút "Đặt Câu Hỏi" bị Discord từ chối 400 Bad Request vì placeholder TextInput dài 106 ký tự (giới hạn 100). Đã rút gọn placeholder và clamp giá trị câu hỏi/bối cảnh cũ xuống 500 ký tự đúng `max_length` khi truyền lại vào modal.
- **Thông Báo Cooldown Thân Thiện**: Handler `tree.error` vốn được đăng ký bên trong event `on_error` (gần như không bao giờ kích hoạt) khiến mọi lỗi `CommandOnCooldown` ném lên default handler → chỉ có traceback ERROR trong log, người dùng không nhận thông báo. Handler nay đăng ký trong `setup_hook`: cooldown trả tin nhắn ephemeral thân thiện kèm số giây chờ, không crash.

---

## [2.7.5] - 2026-09-17 — *Tarot & Embed Hardening - Bounded AI & Secure Startup*

### Fixed
- **Tarot AI JSON Parser (nghiêm trọng)**: Viết lại tầng fallback parse JSON bằng `json.JSONDecoder.raw_decode` theo từng field. Trước đây JSON lỗi khiến câu hỏi bị từ chối (`is_valid: false`) trở lại thành hợp lệ, JSON rác lọt thẳng ra embed và giá trị `null` biến thành chữ "None" trong bài giải. Metadata-only response giờ trả về rỗng thay vì leak.
- **Tarot Safety System Instruction**: Thêm `TAROT_SYSTEM_INSTRUCTION` vào cả 3 config AI (main/fallback/followup) — chống prompt-injection từ câu hỏi/@mention, cấm tuyên bố tương lai/suy nghĩ/tình cảm người khác như sự thật, khung xử lý khủng hoảng, Yes/No chỉ là xu hướng biểu tượng.
- **Tarot Tương Tác**: Chống double-flip bằng `asyncio.Lock` (trước đây bấm 2 nút nhanh gây save history 2 lần); AI task mồ côi được cancel khi gửi bài thất bại/flip lỗi/timeout/cog unload; nút "Hỏi thêm" chỉ mất lượt khi submit modal thành công; embed kết quả giới hạn aggregate 6000 ký tự, bài đọc quá dài giữ nguyên trong attachment `tarot_reading.txt`.
- **Embed Pipeline**: Spoiler luôn che media và cắt chuỗi an toàn markdown; tên author clamp 256 ký tự; `cog_unload` await toàn bộ worker task; delete origin xóa mọi preview liên quan; preview clamp 2000 ký tự; `allowed_mentions=none` chống @everyone ping; media download giới hạn 10MB; NSFW block không còn rơi xuống proxy tầng dưới; yt-dlp không upload manifest HLS/DASH thành mp4 hỏng.
- **Async AI Client**: `bounded_ai_generate()` mới trong `core/ai.py` dùng AsyncClient của google-genai — timeout giờ hủy thật request nền (trước đây `wait_for(to_thread(...))` bỏ thread chạy tiếp ngốn quota); Tarot/Summary/Cabin chuyển hết sang đường đi async; semaphore 6 request đồng thời, MapReduce 3 chunk song song.
- **Summary**: Chunk Map thất bại được đánh dấu "KHÔNG HOÀN THÀNH" thay vì trộn exception text vào tổng hợp; QA Evaluator mode-aware (chế độ short không bị trừ điểm theo timeline/ngưỡng 3500 của long).
- **Config Bảo Mật**: Bot fail startup khi thiếu `ADMIN_PASSWORD`/`FLASK_SECRET_KEY`; xóa mật khẩu admin fallback cứng. ⚠️ Render cần set 2 biến này trước khi deploy.
- **DB Phân Kỳ**: Cảnh báo kèm timestamp giờ VN khi Turso lỗi và bot rớt về Local SQLite (dữ liệu local không tự sync ngược cloud).

---

## [2.7.4] - 2026-09-09 — *Bot Init Safety Lock & Cabin Commands Restoration*

### Fixed
- **Khôi Phục Toàn Bộ Lệnh Cabin (Slash & Prefix Commands)**: Khôi phục 100% các Slash Commands (`/cabin`, `/cabinstop`) và Prefix Commands (`.m cabin`, `.m cabin stop`, `.m cabin list`, `.m cabinstop`, `.m cabinlist`) vốn bị mất trong đợt refactor debounce trước đó. Tích hợp trơn tru toàn bộ logic toggle, khiên bảo vệ, đè quyền với Debounce Batch Engine mới và chuẩn hóa định dạng trả lời `🎙️ **Dịch cabin:**`.
- **Khóa An Toàn Đồng Bộ Lệnh (Command Sync Safety Lock)**: Giải quyết triệt để nguyên nhân gốc rễ khiến Discord xóa lệnh `/cabin` hiện tại và `/tarot` trước đây. Thiết lập danh sách `EXPECTED_CORE_SLASH_COMMANDS`; nếu bất kỳ extension nào nạp lỗi hoặc thiếu lệnh cốt lõi, bot **tự động hủy gọi `tree.sync()` toàn cầu** để bảo vệ tuyệt đối kho lệnh trên Discord không bị xóa sạch.

### Added
- **Cơ Chế Thử Lại Nạp Extension (Retry Backoff)**: Tự động thử lại tối đa 2 lần với độ trễ 1.5s nếu nạp extension gặp sự cố mạng tạm thời tới Turso Cloud.
- **Lệnh Đồng Bộ Thủ Công Cho Quản Trị Viên (`/sync` & `.m sync`)**: Bổ sung Slash Command `/sync` và Prefix Command `.m sync [guild/global]` (Administrator). Cho phép đồng bộ tức thì 0 giây cho máy chủ (`guild_only=True`), giúp khôi phục hoặc kiểm thử lệnh ngay lập tức mà không cần chờ 1 tiếng Discord cache toàn cầu.

---

## [2.7.3] - 2026-09-09 — *Cabin Debounce Batch Engine - Anti-RPM Message Aggregation*

### Changed
- **Debounce Batch Engine cho Dịch Cabin (Anti-RPM)**: Thay thế cơ chế xử lý tức thời từng tin nhắn (`in-flight guard`) bằng hệ thống buffer + debounce 3 giây. Khi nạn nhân gửi nhiều tin liên tiếp, bot gom tất cả vào một batch rồi chỉ gọi AI **1 lần duy nhất** với prompt tổng hợp thay vì N lần - giảm đáng kể số lần gọi API và chống rate limit RPM.
- **`generate_cabin_interpretation_batch()`**: Hàm AI mới trong `features/cabin/ai.py` nhận `List[str]` các tin nhắn, nếu chỉ có 1 tin thì tự động delegate về hàm đơn lẻ (zero overhead), nếu nhiều tin thì sinh prompt tổng hợp với yêu cầu dịch thống nhất tất cả câu nói trong batch.
- **Cooldown Check-Only Guard**: Cooldown được check (không lock) ngay khi nhận tin, chỉ lock thật sự ngay trước khi gọi AI để tránh double-lock khi nhiều tin được buffer trong cùng debounce window.
- **Reply vào tin nhắn cuối cùng trong batch**: Bot luôn reply vào tin nhắn mới nhất của nạn nhân, không phải tin nhắn đầu tiên trigger.
- **Context filter batch-aware**: Tự động loại bỏ tất cả nội dung các tin trong batch khỏi context window để AI không bị lặp lại chính nội dung cần dịch khi xây dựng bối cảnh.
- **Cog cleanup an toàn**: `cog_unload` tự động hủy tất cả debounce tasks đang pending để tránh task leak khi bot reload/restart.

---

## [2.7.2] - 2026-09-09 — *Cabin AI Robustness & Victim-Centric Interpretation Fixes*

### Fixed
- **Sửa Lỗi Crash `ActivityLogger`**: Chuẩn hóa lệnh gọi sang `activity_logger.log(...)` trong `features/cabin/cog.py` và bổ sung bí danh `log_activity = log` trong `core/activity_logger.py` tránh phát sinh `AttributeError`.
- **Triệt Tiêu Lỗi Cụt Câu Dịch Cabin (Token Exhaustion Guard)**: Nâng `max_output_tokens` từ 350 lên 1200 cho Gemini 3.7 / 3.8 Flash, ngăn chặn việc thought tokens làm cạn quota; đồng thời bổ sung bộ lọc `is_incomplete_sentence` và chặn `FinishReason.MAX_TOKENS` tự động fallback khi phát hiện câu dang dở.
- **Tập Trung 100% Vào Câu Nói Nạn Nhân (Victim-Centric Prompt & Narrow Context)**: Thu hẹp `CONTEXT_MAX_MESSAGES` xuống 4 tin nhắn và thời gian xuống 5 phút; tái cấu trúc prompt đặt câu nói của nạn nhân làm trung tâm, triệt tiêu việc AI bị phân tâm bởi các chủ đề thảo luận cũ trong kênh chat.
- **Tối Ưu Cooldown Thông Minh**: Cooldown 8s chỉ bắt đầu đếm sau khi câu dịch đã được gửi thành công; tự động giải phóng cooldown ngay nếu quá trình gọi AI gặp sự cố hoặc timeout để không làm trôi tin nhắn tiếp theo của người dùng.

---

## [2.7.1] - 2026-09-09 — *AI Tarot Interpretation Enhancements & Cabin Takeover Engine*

### Added
- **Cơ Chế Đè Quyền Dịch Cabin & Reset Cooldown (Cabin Takeover)**:
  - Cho phép người dùng khác (C) đè quyền phiên cabin của người trước (A) trên cùng một nạn nhân (B).
  - Tự động gỡ phiên của A ra (giải phóng slot cho A có thể troll người khác) và chuyển nạn nhân B sang danh nghĩa đang bị C troll (tính vào quota 1 phiên của C).
  - Reset bộ đếm thời gian chờ dịch của nạn nhân B về 0 ngay lập tức để người mới C có thể troll ngay tin nhắn đầu tiên mà không bị delay.
  - Phản hồi Embed thông báo trực quan: `🎙️ ĐÃ ĐÈ QUYỀN DỊCH CABIN!` với thông tin người nắm quyền mới và thời gian hết hạn mới.
- **Tiêu Chí Chốt Hạ 2 Chiều Cho Trải Bài Yes/No (`⚡ TIÊU CHÍ CHỐT HẠ`)**:
  - Tích hợp điều kiện cụ thể: Khi nào nên chọn CÓ/LÀM vs. Khi nào nên chọn KHÔNG/BỎ.
  - Quy tắc tự vấn 1 phút giúp người hỏi tự đối diện nội tâm để ra quyết định dứt khoát.
- **Tái Cấu Trúc Trải Bài Celtic Cross 10 Lá Toàn Diện**:
  - Luận giải sâu sắc (>4.000 ký tự) với 5 phần lớn có cấu trúc rõ ràng.
  - Mục `📖 DÒNG CHẢY CÂU CHUYỆN`: Kết nối các trục lá bài (Bản ngã & Thử thách, Nền tảng quá khứ, Ý thức & Tiềm thức, Môi trường & Kỳ vọng) thành một chuỗi diễn biến nhân quả liền mạch thay vì liệt kê rời rạc.
  - Mục `🏆 CÁI KẾT CUỐI CÙNG & ĐÍCH ĐẾN`: Đưa ra kết luận rõ ràng, sắc bén về kết cục và đích đến nếu giữ nguyên tiến trình hiện tại.

### Changed
- **Nâng Cấp Persona Reader Celeste (Healer) Đậm Chất Nữ Tính & Thấu Cảm**:
  - Điều chỉnh tính cách Celeste: Xưng hô dịu dàng, thân thương (*"bạn thương", "người bạn của mình"*), giọng văn nữ tính, đằm thắm, giàu ẩn dụ thơ mộng xoa dịu tâm hồn nhưng vẫn thông tuệ và chỉ lối sáng rõ.
- **Triệt Tiêu Câu Trả Lời Ba Phải / Lấp Lửng Trong Luận Giải Tarot**:
  - Cập nhật nguyên tắc diễn giải: Thay vì buông câu lười biếng *"tùy bạn tự quyết"*, bot luôn vẽ ra bản đồ rẽ nhánh định hướng 2 chiều: nếu chọn Hướng A thì chuẩn bị gì và hành động ra sao; nếu chọn Hướng B thì xử lý thế nào và đón nhận kết quả ra sao. Quyền quyết định luôn ở người hỏi nhưng luôn có lộ trình vững vàng.
- **Dynamic Timeout Cho Trải Bài Lớn**:
  - Tự động tăng thời gian chờ AI lên 26 giây cho các trải bài lớn (từ 5 lá trở lên) để AI hoàn thành trọn vẹn bài phân tích sâu mà không bị ngắt quãng.

---

## [2.7.0] - 2026-09-09 — *Context-Aware AI Cabin Parody Interpretation & Multi-Tier Cascade Engine*

### Added
- **Tính Năng Dịch Cabin Troll AI Trực Tiếp (`/cabin`)**:
  - Khi một thành viên được chỉ định gửi tin nhắn trong kênh chat, bot sẽ đóng vai "phiên dịch viên cabin" song song, tự động đọc tin nhắn và reply phiên dịch sang tầng ý nghĩa châm biếm, bóc trần sự thật ngầm hiểu hoặc bẻ lái siêu hài hước.
  - **Slash Command duy nhất**: `/cabin @user [thoi_gian]` tích hợp cơ chế **Toggle thông minh** (nếu chưa bật thì bật, nếu đang bật thì gõ lại lệnh sẽ tự động tắt giải thoát cho nạn nhân).
  - **Lệnh Prefix linh hoạt**: `.m cabin @user [thời_gian]`, `.m cabinstop @user`, `.m cabinlist`.
  - Định dạng hiển thị trực diện: `🎙️ Dịch cabin: <nội dung bẻ lái>` không chứa các mào đầu dài dòng.
- **Nắm Bắt Ngữ Cảnh Hội Thoại 30 Phút & Góc Nhìn Ngôi Thứ Nhất**:
  - Tự động quét tối đa 25 tin nhắn trong 30 phút gần nhất của kênh chat để AI nắm bắt chủ đề mọi người đang bàn tán (chơi game, than ế, đi ăn, code, drama...).
  - Bản dịch cabin được thực hiện ở **góc nhìn ngôi thứ nhất** (*"Tao/Tôi/Mình/Em"*), tự thú nhận sự thật bựa/sĩ diện/lươn lẹo trúng tim đen.
- **Cơ Chế Chống Phá Hoại & Kiểm Soát Công Bằng (Fair-play Controls)**:
  - **Giới Hạn 1 Người 1 Phiên**: Mỗi người chỉ được mở tối đa 1 phiên cabin tại một thời điểm; muốn troll người khác phải dừng hoặc chờ phiên cũ kết thúc.
  - **🛡️ Khiên Chống Cabin Độc Quyền Quản Trị (Admin Dashboard Immunity)**: Không cung cấp lệnh chat công khai để tránh lạm dụng làm mất vui. Quản trị viên quản lý cấp/gỡ khiên bảo vệ cho các thành viên đặc biệt trực tiếp từ Admin Web Console.
  - **Tab Quản Trị Dịch Cabin Mới Trên Web Dashboard**: Theo dõi các phiên cabin đang chạy trực tiếp (Live Sessions), dừng cưỡng chế từ xa và quản lý danh sách Khiên miễn nhiễm theo Server.
  - **Nút Bấm Dừng 1-Chạm (`🛑 Dừng Cabin`) & Lệnh Dừng Nhanh (`/cabinstop`)**: Cho phép nạn nhân, người bật hoặc Quản trị viên dừng phiên tức thì.
  - **Cooldown Anti-Spam (8 giây)**: Giới hạn tần suất phản hồi khi cùng một nạn nhân spam liên tục, bảo vệ tài nguyên API và không làm flood kênh chat.
  - **Lưu Trữ Bền Vững (Database Persistence)**: Quản lý các phiên cabin qua bảng `cabin_sessions` và khiên qua `cabin_shields` trong Turso LibSQL Cloud / Local SQLite, tự động dọn dẹp khi hết hạn.
  - **Showcase Trang Khách & Trợ Giúp**: Bổ sung thẻ giới thiệu tính năng trên Public Landing Page và menu trợ giúp tương tác `.m` / `/help`.

### Changed
- **Chuỗi Fallback 7 Tầng Toàn Diện Cho Toàn Bộ Hệ Thống**:
  - Chuẩn hóa thứ tự fallback ưu tiên áp dụng đồng bộ cho Tarot, Dịch Cabin, Tóm tắt tin nhắn (Single-Pass & MapReduce) và AI QA Evaluator:
    1. `gemini-3.8-flash` (Ưu tiên 1 - Tối ưu nhất)
    2. `gemini-3.7-flash` (Ưu tiên 2)
    3. `gemini-3.6-flash` (Ưu tiên 3)
    4. `gemini-3.5-flash` (Ưu tiên 4)
    5. `gemini-3.5-flash-lite` (Ưu tiên 5)
    6. `gemini-3.1-flash-lite` (Ưu tiên 6)
    7. `gemma-4-31b-it` (Ưu tiên 7 - Fallback cuối cùng)
- **Cập Nhật Mô Hình Mặc Định**:
  - Chuyển mô hình mặc định của Tarot, Cabin, Tóm tắt tin nhắn và QA Evaluator sang `gemini-3.8-flash`.
- **Tăng Cường Độ Bền Bỉ Cho AI Summary**:
  - Bổ sung wrapper `_generate_with_fallback` cho cả Single-Pass và MapReduce Reduce, tự động chuyển model tiếp theo khi gặp timeout hoặc lỗi quota 429/503.
- **Đồng Bộ Web Dashboard & Biến Môi Trường**:
  - Giao diện Admin Console Overview và thẻ Engine Cabin tự động hiển thị model hiện hành và hỗ trợ cập nhật động qua API `/api/stats`.
  - Cập nhật tài liệu cấu hình mẫu `.env.example`.

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
