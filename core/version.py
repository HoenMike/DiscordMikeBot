"""
core/version.py - Quản lý phiên bản (Semantic Versioning) và Nhật ký phát hành (Patchnotes / Changelog).

Quy tắc phiên bản: Major.Minor.BugFix (Ví dụ: 2.4.1)
- Major: Đại tu kiến trúc hoặc thay đổi nền tảng lớn (1.x.x -> 2.0.0)
- Minor: Bổ sung tính năng mới hoặc nâng cấp module lớn (2.0.0 -> 2.1.0)
- BugFix: Sửa lỗi / Hotfix / Tinh chỉnh cho phiên bản hiện tại (2.4.0 -> 2.4.1)
"""

from typing import Dict, List, Any, Optional
import discord

from core.branding import BOT_BRAND_NAME

CURRENT_VERSION = "3.7.5"
RELEASE_DATE = "2026-10-08"
CODENAME = "Asumi 3.7.4 - Compact Search Results"

# Lịch sử chi tiết các phiên bản phát hành được đồng bộ trực tiếp từ Git Commit History (Mới nhất nằm ở đầu)
CHANGELOG: List[Dict[str, Any]] = [
    {
        "version": "3.7.4", "date": "2026-10-08",
        "type": "bugfix", "title": "Brave Search Presentation & Result Quality",
        "summary": "Trả lời trước, chỉ 3 nguồn có link rõ ràng; bỏ HTML rác và kết quả dài.",
        "changes": [
            {"category": "🔎 Brave Search UX", "items": [
                "Brave trả Discord embed gọn: câu trả lời ngắn, tối đa 3 nguồn và link gốc.",
                "Rút bớt nội dung lặp; làm sạch HTML như strong và trích dẫn [1] không có link.",
                "Với giá xăng Việt Nam mới nhất, mở rộng keyword tìm đúng bảng giá và kỳ điều hành, không tăng request.",
                "Ưu tiên nguồn công bố trực tiếp trong phần hiển thị, giảm trang tổng hợp hoặc biểu đồ cũ.",
                "Không bịa giá hiện tại khi trích đoạn thiếu số liệu/ngày phù hợp.",
            ]},
        ],
    },
    {
        "version": "3.7.3", "date": "2026-10-08",
        "type": "bugfix", "title": "Code-owned Assistant Configuration",
        "summary": "Chỉ giữ secrets/kết nối trong Environment; search/model/limits bật và cấu hình bằng core/constants.py.",
        "changes": [
            {"category": "⚙️ Configuration", "items": [
                "Asumi models, cooldown, caching, quotas, feature policy moved to core/constants.py.",
                "Brave activates with BRAVE_SEARCH_API_KEY when durable Turso quota is ready; no extra feature flag.",
                "Discord History / Clef select feature policy in code, still gated by bot token or Cloudflare credentials.",
                "Semantic Archive remains off by policy until live Vectorize verification.",
            ]},
            {"category": "🔎 Search UX", "items": [
                "Giá xăng hôm nay và một số giá công khai có tín hiệu thời gian rõ ràng route Brave trực tiếp.",
                "Thiếu Brave key: giải thích cần thêm key, không tuyên bố rằng Search chưa được tích hợp.",
                "Giữ bảo vệ tin nhắn Discord, hạn mức 500 request/tháng, cache và không request tính phí khi DB quota không bền vững.",
            ]},
        ],
    },
    {
        "version": "3.7.2", "date": "2026-10-08",
        "type": "bugfix", "title": "Search Follow-up and Dashboard (T22.4b)",
        "summary": "Reply vào kết quả tìm kiếm rõ nguồn hơn, thêm explicit web follow-up và telemetry tìm kiếm.",
        "changes": [
            {"category": "🔎 Search UX", "items": [
                "Nhận câu tìm tiếp trên web với từ khóa công khai cụ thể, vẫn qua Brave quota và privacy gate.",
                "Reply kết quả Discord History có thêm channel và source context đã xác minh.",
                "Chat follow-up chỉ giải thích nguồn đã thấy; không tự động search mới hoặc suy đoán nội dung.",
            ]},
            {"category": "📊 Observability", "items": [
                "Dashboard hiển thị trạng thái Brave/Discord History, số nguồn, cache, quota và API calls.",
                "Giữ logs không chứa truy vấn và nội dung tin nhắn riêng tư.",
                "Các provider vẫn tắt mặc định đến khi được kiểm thử live.",
            ]},
        ],
    },
    {
        "version": "3.7.1", "date": "2026-10-08",
        "type": "bugfix", "title": "Temporal Discord History Search (T22.4a)",
        "summary": "Tìm tin nhắn cũ nhất/mới nhất của một người, có hoặc không có từ khóa, bằng Discord Search.",
        "changes": [
            {"category": "🔎 Discord History", "items": [
                "Hỏi tin nhắn đầu tiên hoặc gần nhất của @user; mặc định trả một tin có Jump to Message.",
                "Hỏi 5 tin nhắn đầu tiên hoặc lần đầu @user nhắc tới một chủ đề; sắp xếp theo timestamp.",
                "Giữ giới hạn API/time/ACL và ghi rõ đây là tin sớm nhất tìm được, không bảo đảm tuyệt đối.",
                "Cần bật ASUMI_DISCORD_HISTORY_ENABLED và nghiệm thu API bot thật mới sử dụng được.",
            ]},
        ],
    },
    {
        "version": "3.7.0", "date": "2026-10-08",
        "type": "minor", "title": "Intelligent Source Routing",
        "summary": "T22.3: Clef chọn nguồn Brave/Discord History/Archive có gate an toàn và synthesis nguồn công khai.",
        "changes": [
            {"category": "🧠 Source selection", "items": [
                "Clef phân loại web_search, discord_history hoặc archive_search theo câu hỏi; không gọi API ngoài nếu chưa bật feature flag.",
                "Web auto-search chỉ cho câu hỏi thông tin công khai có dấu hiệu cần dữ liệu mới; Discord/Archive tách biệt.",
                "Brave tự động có thể tổng hợp ngắn từ kết quả công khai rồi đưa URL nguồn thực tế.",
            ]},
            {"category": "🛡️ Privacy & availability", "items": [
                "Không chuyển Discord private references hoặc reply mơ hồ vào Brave auto-search.",
                "Không mở tool lại khi reply follow-up trừ explicit action; lỗi synthesis fallback về kết quả nguồn thật.",
                "Auto-search OFF theo mặc định; provider gốc cũng phải bật riêng.",
            ]},
        ],
    },
    {
        "version": "3.6.0", "date": "2026-10-08",
        "type": "minor", "title": "Discord History Search",
        "summary": "T22.2: tìm tin nhắn lịch sử chưa lưu Archive theo người/thời gian/chủ đề và mở tin nhắn gốc.",
        "changes": [
            {"category": "🔎 Discord History", "items": [
                "Tìm xem đầu năm @user có nói gì về mua xe không: trả kết quả thật từ Discord Search.",
                "Mỗi kết quả có tác giả, ngày và Jump to Message; không cần lưu Archive từ trước.",
            ]},
            {"category": "🔒 Privacy", "items": [
                "Chỉ cho thấy message ở kênh mà người hỏi và bot cùng có quyền xem lịch sử.",
                "Mặc định OFF để kiểm tra API bot/permission trước khi enable live; không passive index.",
            ]},
        ],
    },
    {
        "version": "3.5.0", "date": "2026-10-08",
        "type": "minor", "title": "Brave Web Search",
        "summary": "T22.1: tìm web thủ công qua Brave, trả URL nguồn thật và kiểm soát quota bền vững.",
        "changes": [
            {"category": "🔎 Web", "items": [
                "@Asumi tìm trên web ... lấy kết quả từ Brave, không tự gọi search cho chat thường.",
                "Kết quả có tiêu đề, đoạn trích và URL nguồn.",
            ]},
            {"category": "🛡️ Safety", "items": [
                "Brave mặc định OFF, cần API key + flag; monthly DB quota tối đa 900, mặc định 500.",
                "Không gửi nội dung riêng tư Discord/Archive sang Brave, có cooldown + cache + fail-closed.",
            ]},
        ],
    },
    {
        "version": "3.4.1",
        "date": "2026-10-08",
        "type": "bugfix",
        "title": "Conversational Timeout Budget",
        "summary": "Giảm thời gian chờ khi Gemini chat treo và làm telemetry timeout rõ nguyên nhân hơn.",
        "changes": [
            {"category": "⚡ Chat reliability", "items": [
                "Conversation dùng hard total AI budget thay vì cho mỗi fallback model một timeout đầy đủ.",
                "Mặc định mỗi model tối đa 4s, toàn bộ AI chat tối đa 8s, 2 attempts.",
                "Fallback chat ưu tiên gemini-3.1-flash-lite trước model nặng hơn.",
                "Attempt sau chỉ dùng phần budget còn lại; hết budget thì dừng ngay.",
            ]},
            {"category": "📊 Diagnostics", "items": [
                "Timeout log ghi ai_ms riêng thay vì chỉ total_ms.",
                "Telemetry ghi models tried, attempts, total budget và last error type.",
                "Dashboard gắn nhãn AI budget timeout để phân biệt với Clef/router latency.",
            ]},
        ],
    },
    {
        "version": "3.4.0",
        "date": "2026-10-08",
        "type": "minor",
        "title": "Intelligence Polish",
        "summary": "Hoàn thiện observability, semantic fallback visibility và concurrency guard cho Asumi Intelligence.",
        "changes": [
            {"category": "📊 Observability", "items": [
                "Asumi AI telemetry ghi Archive save/search/forget, lexical vs semantic-hybrid/fallback, semantic latency và match counts.",
                "Dashboard hiển thị Archive mode/Vector latency ngay trên activity row; semantic fallback được tô cảnh báo.",
                "Clef error/low-confidence fallback được hiển thị rõ thay vì chỉ có timing.",
                "Telemetry tiếp tục không lưu nguyên prompt/response hay Archive content.",
            ]},
            {"category": "🛡️ Reliability", "items": [
                "Vectorize query trả typed status report để phân biệt ok/no-match/permission-error/unavailable.",
                "Semantic request có concurrency cap mặc định 3 để chống burst Save/Search.",
                "Index initialization được serialize để tránh race auto-create ở first request.",
                "Load smoke test khóa concurrency guard và regression tests cover lexical fallback metrics.",
            ]},
        ],
    },
    {
        "version": "3.3.1",
        "date": "2026-10-08",
        "type": "bugfix",
        "title": "Archive Semantic Retrieval",
        "summary": "Thêm semantic retrieval tùy chọn cho Archive bằng Workers AI + Vectorize, luôn fallback về lexical nếu Cloudflare chưa bật hoặc lỗi.",
        "changes": [
            {"category": "🧠 Semantic Archive", "items": [
                "BGE-M3 tạo embedding đa ngôn ngữ; Vectorize tìm nội dung gần nghĩa thay vì chỉ exact keyword.",
                "Hybrid search ưu tiên semantic match rồi bổ sung lexical result, dedupe và giới hạn 5 mục.",
                "Vectorize chỉ lưu derived vector/Archive ID theo namespace user; nội dung thật luôn đọc lại từ canonical Turso/SQLite.",
                "Save/Forget đồng bộ Vectorize best-effort trong nền; lỗi semantic không làm hỏng Archive Core.",
            ]},
            {"category": "🔒 Fail-closed", "items": [
                "Semantic mặc định OFF và cần CF_ARCHIVE_SEMANTIC_ENABLED=true.",
                "Hỗ trợ CLOUDFLARE_VECTORIZE_TOKEN riêng để không thay token Workers AI/Clef đang chạy.",
                "Thiếu quyền hoặc lỗi Vectorize sẽ circuit-break semantic và tiếp tục search lexical.",
            ]},
        ],
    },
    {
        "version": "3.3.0",
        "date": "2026-10-08",
        "type": "minor",
        "title": "Asumi Archive Core",
        "summary": "Thêm bộ nhớ dài hạn explicit: Save / Search / Forget theo từng user, không archive chat ngầm.",
        "changes": [
            {"category": "🧠 Archive", "items": [
                "Reply message/link/ảnh rồi nói @Asumi nhớ cái này để lưu source + metadata + Jump to Message.",
                "Tìm lại Archive bằng câu tự nhiên như @Asumi tìm lại meme mèo Khai; trả tối đa 5 kết quả.",
                "Xóa bằng @Asumi quên #ID; delete luôn scope theo owner_user_id nên user không thể xóa Archive của người khác.",
                "Cùng một Discord message được dedupe cho cùng owner; save lại có thể cập nhật note thay vì tạo bản trùng.",
            ]},
            {"category": "🔒 Privacy & storage", "items": [
                "Bare save phrase không reply/link/ảnh sẽ bị từ chối; Asumi không tự chọn nearby chat để lưu.",
                "Canonical records dùng database adapter hiện có (Turso Cloud / SQLite fallback), không tạo thêm split-brain D1.",
                "Slice 3.3.0 chỉ lưu metadata/URL của media, chưa copy binary sang R2.",
                "Archive search/delete chỉ truy vấn dữ liệu thuộc user đã lưu.",
            ]},
        ],
    },
    {
        "version": "3.2.1",
        "date": "2026-10-07",
        "type": "bugfix",
        "title": "Tarot finalizing UX hotfix",
        "summary": "Làm rõ trạng thái Tarot đang chạy và rút gọn kết quả Daily/1 lá để user không phải đoán bot đã xong chưa.",
        "changes": [
            {"category": "🔮 Tarot UX", "items": [
                "Khi đã lật hết nhưng AI chưa xong, trạng thái ĐANG LUẬN GIẢI — CHƯA XONG nằm ngay trên Reading Board thay vì bị đẩy xuống dưới ảnh.",
                "Hiển thị rõ rằng phần lật bài đã xong, Asumi vẫn đang viết luận giải và user không cần bấm gì thêm; message sẽ tự cập nhật.",
                "Daily / Single / Yes-No 1 lá dùng một embed gọn: trạng thái HOÀN TẤT + lá bài + luận giải xuất hiện trước ảnh, giảm scroll và bỏ block thông tin trùng.",
                "Yes/No compact result vẫn giữ phán quyết; multi-card spreads giữ layout chi tiết hai embed hiện tại.",
            ]},
        ],
    },
    {
        "version": "3.2.0",
        "date": "2026-10-07",
        "type": "minor",
        "title": "Context + Lens",
        "summary": "Asumi hiểu reply/recent context có chọn lọc, link/embed metadata và ảnh; follow-up đúng live session không reroute thành action mới.",
        "changes": [
            {"category": "🧠 Context", "items": [
                "Reply vào một message rồi tag Asumi sẽ đưa đúng message đó vào context.",
                "Recent channel history chỉ được fetch khi câu hỏi có cue như cái này/cái trước/phía trên/vừa rồi, với số message và character budget bị giới hạn.",
                "Reply đúng response conversational mới nhất tiếp tục session mà không gọi Clef/tool router lại; reply cũ, khác user hoặc session hết hạn không được tiếp tục.",
                "Output từ natural-language Tarot/Summary cũng được bridge vào session; reply vào bất kỳ chunk/output được capture đều có thể follow-up mà không mở action mới.",
            ]},
            {"category": "🖼️ Image Lens", "items": [
                "Nhận PNG/JPEG/WEBP từ attachment trực tiếp hoặc message được reply.",
                "Ảnh được gửi multimodal vào Gemini 3.5 Flash-Lite; image-only mention cũng vào vision chat thay vì mở Help.",
                "Ảnh gần nhất có thể được giữ tạm trong RAM của live session để follow-up như 'vậy sửa chỗ nào?' vẫn hiểu ảnh cũ; không persist DB/R2.",
            ]},
            {"category": "🔗 Link Lens", "items": [
                "Thu thập URL từ current/reply/recent context và bật Gemini URL Context khi có link.",
                "Đọc metadata Discord embed/attachment làm fallback context cho các social link khó fetch trực tiếp.",
            ]},
            {"category": "🔒 Bounds & privacy", "items": [
                "Mặc định recent context tối đa 8 messages / 7000 chars; image context tối đa 2 ảnh / 5 MiB mỗi ảnh.",
                "Context chỉ dùng just-in-time; telemetry dashboard tiếp tục không lưu nguyên prompt/response.",
                "Audio/voice vẫn ngoài scope Asumi 3.x.",
            ]},
        ],
    },
    {
        "version": "3.1.2",
        "date": "2026-10-07",
        "type": "bugfix",
        "title": "Dashboard AI telemetry",
        "summary": "Đưa latency telemetry của @Asumi vào Admin Dashboard hiện có thay vì phải đọc Render Logs.",
        "changes": [
            {"category": "📊 Dashboard", "items": [
                "Thêm filter Asumi AI trong Log Tương Tác.",
                "Mỗi @Asumi request hiển thị tổng thời gian, model và AI/Clef latency ngắn gọn ngay trên bảng.",
                "Modal Chi tiết lưu route_ms, clef_ms, ai_ms, send_ms, total_ms, model, attempts, source và intent.",
            ]},
            {"category": "🔒 Privacy", "items": [
                "Telemetry Asumi không lưu nguyên prompt/response; chỉ lưu metadata hiệu năng, user/server/channel và kích thước input/output.",
            ]},
        ],
    },
    {
        "version": "3.1.1",
        "date": "2026-10-07",
        "type": "bugfix",
        "title": "Conversational latency hotfix",
        "summary": "Giảm độ trễ @Asumi: dùng Gemini 3.5 Flash-Lite cho chat thường, bỏ Clef ở greeting/test rõ ràng, giới hạn fallback và thêm timing telemetry.",
        "changes": [
            {"category": "⚡ Conversational latency", "items": [
                "Chat thường mặc định dùng gemini-3.5-flash-lite để ưu tiên RPD/throughput; 3.8 Flash chỉ còn fallback khi cần.",
                "Greeting/test rõ ràng như hello/hi/ping bỏ qua Clef để tránh thêm một network round-trip.",
                "Mỗi model conversational timeout mặc định 6 giây và tối đa 2 attempts để tránh fallback chain kéo dài.",
            ]},
            {"category": "📈 Observability", "items": [
                "Render logs giờ có Asumi Timing cho route_ms, clef_ms, ai_ms, send_ms và total_ms.",
                "Log AI ghi model, số attempt và thời gian từng model để xác định bottleneck nhanh.",
            ]},
        ],
    },
    {
        "version": "3.1.0",
        "date": "2026-10-07",
        "type": "minor",
        "title": "Conversational Core",
        "summary": "Thêm conversational entrypoint @Asumi với reply continuation, bounded session, typed tool routing và Clef-flash optional router; command cũ vẫn luôn được ưu tiên.",
        "changes": [
            {"category": "💬 Conversational UX", "items": [
                "Có thể tag @Asumi rồi nói tự nhiên; câu không khớp command sẽ đi vào assistant thay vì bị bỏ qua.",
                "Reply trực tiếp response conversational gần nhất để tiếp tục session ngắn 20 phút mà không cần tag lại.",
                "Normal chat không tag/reply không kích hoạt assistant; slash/.m/mention command hợp lệ vẫn chạy deterministic trước AI.",
            ]},
            {"category": "🧰 Tool routing", "items": [
                "Natural language có thể route vào Help, Tarot launcher/Daily và Summary/Catch-up bằng command bridge dùng chính command engine hiện tại.",
                "Command bridge dùng synthetic message copy nên không mutate gateway message và vẫn giữ checks/cooldowns của command cũ.",
                "Daily mention flow bỏ qua filler tự nhiên như đi/nha/cho tôi để không biến filler thành câu hỏi Tarot.",
            ]},
            {"category": "☁️ Cloudflare-ready", "items": [
                "Thêm optional Clef-flash decision router qua Workers AI REST API, disabled-by-default khi chưa có Cloudflare credentials.",
                "Thiếu key, timeout hoặc confidence thấp sẽ fail safe về local router + AI path hiện tại; deterministic commands không phụ thuộc Cloudflare.",
                "Audio/voice transcription không nằm trong roadmap 3.x; image input được giữ cho Asumi 3.2.",
            ]},
        ],
    },
    {
        "version": "3.0.1",
        "date": "2026-10-05",
        "type": "bugfix",
        "title": "Tarot renderer title hotfix",
        "summary": "Sửa Reading Board bị cắt tên spread dài bằng dấu ...; title giờ giữ nguyên nội dung và tự fit font hoặc wrap tối đa hai dòng.",
        "changes": [
            {"category": "🖼️ Tarot Reading Board", "items": [
                "Bỏ hard truncate 44 ký tự ở spread title, nên các tên dài như Mind - Body - Spirit không còn bị cắt bằng dấu ba chấm.",
                "Header tự giảm cỡ chữ vừa phải trước; nếu vẫn dài sẽ wrap tối đa hai dòng thay vì mất nội dung.",
                "Áp dụng cùng logic cho Reading Board, visual fallback và Clarifier Board.",
                "Thêm regression cho bilingual fixed-spread title và Smart Custom Spread title dài.",
            ]},
        ],
    },
    {
        "version": "3.0.0",
        "date": "2026-10-05",
        "type": "major",
        "title": "Asumi 3.0 — Tarot-first UX",
        "summary": "Nâng Asumi lên major version 3.0 sau Tarot 2.x: launcher ưu tiên câu hỏi và Daily quick start, recommendation vào quẻ một chạm nhưng vẫn giữ toàn bộ direct/manual flow cũ.",
        "changes": [
            {"category": "🔮 Tarot launcher mới", "items": [
                "Launcher mở bằng hai primary path rõ ràng: Nhập câu hỏi hoặc Daily hôm nay.",
                "Sau khi nhập câu hỏi, Asumi hiển thị spread đề xuất và nút Trải theo đề xuất bắt đầu quẻ ngay trong một click.",
                "Daily hôm nay bắt đầu ngay từ launcher, không cần nhập câu hỏi; /tarot spread:Daily Card và .m tarot daily vẫn hoạt động.",
            ]},
            {"category": "⚙️ UX & compatibility", "items": [
                "Manual spread và Reader Style được chuyển xuống Tuỳ chọn nâng cao thay vì chiếm vị trí đầu launcher.",
                "Custom Spread, History, Journey, follow-up, Why, Clarifier và Recap giữ nguyên.",
                "Slash /tarot và prefix .m tarot dùng cùng launcher; .m tarot <câu hỏi> tiếp tục mở launcher với recommendation tự động.",
                "Nếu Daily/recommendation bị chặn bởi cooldown, launcher khôi phục state để người dùng có thể thao tác lại bình thường.",
            ]},
            {"category": "📚 Help & release", "items": [
                "Help và README có quick-start riêng cho câu hỏi, Daily và direct spread flow.",
                "Tarot 2.x vẫn là engine/feature generation; Asumi 3.0.0 là repository-wide major release.",
            ]},
        ],
    },
    {
        "version": "2.10.0",
        "date": "2026-10-05",
        "type": "minor",
        "title": "Tarot 2.1",
        "summary": "Hoàn tất T20.6–T20.9: phiên đọc nhiều lượt, Smart Custom Spread, Tarot Journey 30 ngày và Recap Card gọn để lưu/chia sẻ.",
        "changes": [
            {"category": "💬 Reading Session", "items": [
                "Mỗi quẻ hỗ trợ tối đa 3 follow-up có context liên tục; clarifier đã delivery trở thành context cho câu hỏi sau nhưng vẫn giữ giới hạn 1/1.",
                "Nút Vì sao? giải thích dựa trên lá/vị trí nhìn thấy, owner-only và không hiển thị suy luận nội bộ.",
                "Session timeout khóa các action tương tác; lỗi generate/delivery không âm thầm tiêu lượt follow-up.",
            ]},
            {"category": "🧩 Smart Custom Spread", "items": [
                "Launcher có Trải bài riêng: AI chỉ thiết kế schema 3–7 vị trí, deck engine mới là nơi rút lá thật.",
                "Validator chặn duplicate, text vượt giới hạn, card/orientation do model cung cấp và framing xâm phạm đời tư; schema lỗi fallback về spread chuẩn.",
                "Custom title đi xuyên live/final Reading Board và Clarifier Board; renderer dynamic hiện có được tái sử dụng.",
            ]},
            {"category": "🧭 Tarot Journey", "items": [
                "Thêm /tarot_journey và .m tarot journey với summary 30 ngày từ lịch sử đã lưu.",
                "Hiển thị suit mix, Major ratio, lá lặp/lá ngược lặp, topic progression và spread dùng nhiều nhất.",
                "Journey Card nhấn mạnh đây là thống kê tự phản chiếu, không phải dự đoán số phận hay chẩn đoán.",
            ]},
            {"category": "📌 Recap & polish", "items": [
                "Kết quả quẻ có Recap Card owner-only: hero/key card, headline, một takeaway, spread và ngày; không gọi AI thêm.",
                "Recap dùng layout portrait save/share-friendly và không nhét toàn bộ luận giải vào ảnh.",
                "Tài liệu/handoff/help được đồng bộ để T20.1–T20.9 có thể tiếp tục bảo trì từ repository mà không cần chat cũ.",
            ]},
        ],
    },
    {
        "version": "2.9.0",
        "date": "2026-10-04",
        "type": "minor",
        "title": "Tarot 2.0",
        "summary": "Hoàn tất release boundary T20.1–T20.5: Asumi đọc quẻ tự nhiên hơn, launcher question-first, live reading session, Reading Board 2.0 và Clarifier 1/1 không reroll quẻ gốc.",
        "changes": [
            {"category": "🔮 Tarot 2.0", "items": [
                "Reading Engine 2.0 nối ý giữa các lá, giữ uncertainty rõ ràng và dùng structured result để UI/renderer tái sử dụng an toàn.",
                "Launcher question-first đề xuất spread theo câu hỏi nhưng vẫn giữ manual override và tương thích slash/prefix hiện có.",
                "Live Reading Session dùng một message chính, progress/micro-reveal, AI-ready state và Reading Board responsive cho 1/3/5/10 lá cùng dynamic layouts.",
            ]},
            {"category": "🃏 Clarifier", "items": [
                "Sau quẻ hoàn tất, chủ quẻ có thể chọn đúng một vị trí để rút một lá Clarifier; target AI gợi ý được ưu tiên trong picker.",
                "Clarifier loại toàn bộ lá gốc khỏi pool, không thay đổi order/chiều/kết quả spread cũ và được bind deterministic để retry không âm thầm reroll.",
                "Clarifier Board giữ nguyên original spread, đánh dấu TARGET và hiển thị quan hệ TARGET → CLARIFIER; AI chỉ giải lớp bổ sung thay vì viết lại toàn quẻ.",
                "Lượt 1/1 chỉ bị tiêu sau khi Discord nhận được Clarifier; lỗi render/AI/delivery giữ nguyên quẻ gốc và cho phép thử lại.",
            ]},
            {"category": "🧪 Reliability & compatibility", "items": [
                "Persist Clarifier đã giao thành công riêng khỏi tarot_history; metadata gốc không bị mutation.",
                "Giới hạn output Clarifier để không vượt Discord embed và fallback text khi attachment gửi thất bại.",
                "Giữ nguyên 9 spread keys, Daily cooldown, history/memory, card fatigue, follow-up hiện có và toàn bộ social-embed v2.8.5.",
            ]},
        ],
    },
    {
        "version": "2.8.5",
        "date": "2026-10-04",
        "type": "bugfix",
        "title": "Universal embed controls",
        "summary": "Đưa bộ điều khiển Reload / Bỏ embed từ Facebook sang toàn bộ provider auto-embed; chỉ người gửi link gốc được thao tác và có thể quay về native Discord embed bất kỳ lúc nào.",
        "changes": [
            {"category": "🪝 Auto-Embed UX", "items": [
                "Mọi preview do API, proxy hoặc yt-dlp tạo ra đều có hai nút 🔄 Reload và 🗑️ Bỏ embed.",
                "Cả hai nút dùng owner-only interaction: user khác người gửi link gốc chỉ nhận cảnh báo ephemeral và không thể thay đổi preview.",
                "Reload giữ preview hiện tại nếu lần tải lại thất bại; provider ngoài Facebook chạy lại pipeline đúng URL, còn Facebook tiếp tục roll sang proxy kế tiếp và không tự nhảy yt-dlp.",
                "Bỏ embed unsuppress message gốc để Discord render native embed rồi dọn toàn bộ preview Asumi của message, tránh duplicate khi một message có nhiều social URL.",
            ]},
            {"category": "🧪 Regression", "items": [
                "Thêm coverage cho action view ở provider ngoài Facebook, reload non-Facebook và native revert cleanup.",
                "Giữ nguyên Facebook proxy rotation, NSFW guards, deletion lifecycle và fallback behavior hiện tại.",
            ]},
        ],
    },
    {
        "version": "2.8.4",
        "date": "2026-10-04",
        "type": "bugfix",
        "title": "Compact Facebook proxy hyperlink",
        "summary": "Rút gọn dòng preview Facebook: URL proxy dài được giấu trong chính tên domain clickable, vẫn giữ nút Proxy khác và proxy-roll flow của v2.8.3.",
        "changes": [
            {"category": "🪝 Facebook Embed", "items": [
                "Hiển thị proxy dưới dạng masked link [facebed.domain](proxy-url) thay vì in toàn bộ URL dài trên dòng riêng.",
                "Không dùng dạng <url> trong target để tránh suppress Discord link preview.",
                "Spoiler bọc toàn bộ masked link thay vì chèn spoiler marker vào URL đích.",
                "Áp dụng cùng format cho preview đầu tiên và mọi lần bấm Proxy khác.",
            ]},
            {"category": "🧪 Regression", "items": [
                "Cập nhật test cho compact proxy link và spoilered masked link.",
                "Giữ nguyên owner-only proxy roll, không auto-roll và không yt-dlp cho Facebook.",
            ]},
        ],
    },
    {
        "version": "2.8.3",
        "date": "2026-10-04",
        "type": "bugfix",
        "title": "Facebook raw proxy embed + manual proxy roll",
        "summary": "Sửa flow Facebook đúng bản chất Discord unfurl: bot phải gửi URL proxy dạng raw để Discord dựng embed; nút chỉ là điều khiển phụ để người gửi chuyển sang proxy kế tiếp, không còn nhảy sang yt-dlp.",
        "changes": [
            {"category": "🪝 Facebook Embed", "items": [
                "Proxy URL Facebook được gửi nguyên dạng trên một dòng riêng thay vì masked markdown, để Discord có thể tự unfurl thành native embed/video.",
                "Nút đổi thành 🔄 Proxy khác và chỉ người gửi link gốc được dùng.",
                "Mỗi lần bấm sẽ roll sang proxy Facebook kế tiếp trong PROXY_DOMAINS/guild override; proxy cũ chỉ bị dọn sau khi proxy mới đã gửi thành công.",
                "Facebook không còn nằm trong yt-dlp fallback path; hết proxy thì bot báo hết proxy thay vì chuyển thẳng sang yt-dlp.",
                "Sau khi đã gửi một proxy, bot không tự đánh giá rồi roll tiếp nữa; người dùng quyết định có cần đổi proxy hay không.",
            ]},
            {"category": "🧪 Regression", "items": [
                "Bổ sung test raw URL unfurl, owner-only proxy button, proxy rotation state và guard không gọi yt-dlp cho Facebook.",
                "Giữ automatic yt-dlp fallback cho các nền tảng khác như Twitter/TikTok/Instagram/Reddit/Twitch.",
            ]},
        ],
    },
    {
        "version": "2.8.2",
        "date": "2026-10-04",
        "type": "bugfix",
        "title": "Facebook fallback bằng Discord Button",
        "summary": "Thay hyperlink fallback v2.8.1 bằng nút Discord native để fallback hoạt động trực tiếp trong chat, chỉ người gửi link gốc được kích hoạt và không còn phụ thuộc public web route.",
        "changes": [
            {"category": "🪝 Facebook Embed", "items": [
                "Thay hyperlink [fallback] bằng nút ↪️ Fallback trên preview Facebook.",
                "Chỉ Discord user đã gửi link gốc được bấm; người khác nhận phản hồi ephemeral và không kích hoạt yt-dlp.",
                "Nút disable ngay khi xử lý, được bật lại nếu fallback thất bại; preview cũ chỉ bị dọn sau khi replacement gửi thành công.",
                "Giữ nguyên fix chống false fallback: Facebook không auto yt-dlp và generic card sớm vẫn được chờ hết grace window.",
            ]},
            {"category": "🧹 Dọn hạ tầng hyperlink", "items": [
                "Xóa signed-token helper, web fallback routes và ASUMI_PUBLIC_URL/PUBLIC_BASE_URL vì không còn cần.",
                "Cleanup manual fallback được track trực tiếp theo (origin message, URL), an toàn khi một message có nhiều link.",
                "Cập nhật regression tests, README và docs/EMBED_PIPELINE.md.",
            ]},
        ],
    },
    {
        "version": "2.8.1",
        "date": "2026-10-04",
        "type": "bugfix",
        "title": "Facebook fallback thủ công bằng hyperlink",
        "summary": "Facebook không còn tự chuyển sang yt-dlp khi Discord chưa kịp xác nhận Facebed. Preview proxy được giữ lại khi unfurl chưa chắc chắn và người dùng có hyperlink fallback nhỏ gọn để tự kích hoạt khi thật sự cần.",
        "changes": [
            {"category": "🪝 Facebook Embed", "items": [
                "Không còn tự động chạy yt-dlp cho Facebook sau lỗi/timeout proxy; các nền tảng khác giữ nguyên fallback tự động.",
                "Generic/login card ở poll sớm không còn fail-fast; Asumi chờ hết grace window để Discord có cơ hội nâng cấp thành preview/video thật.",
                "Nếu Facebed đã gửi nhưng Discord vẫn chưa xác nhận unfurl kịp thời, Asumi giữ preview thay vì xóa nó và thay bằng card fallback kém chất lượng.",
                "Thêm hyperlink [fallback] ngắn gọn trên preview Facebook; link dùng token ký, hết hạn sau 15 phút và chỉ POST mới kích hoạt thay đổi trạng thái.",
                "Fallback thủ công chỉ dọn preview cũ sau khi yt-dlp đã gửi preview mới thành công; nếu thất bại thì preview hiện tại vẫn được giữ.",
            ]},
            {"category": "🧪 Kiểm thử & vận hành", "items": [
                "Bổ sung test cho race condition unfurl Facebook, flow action_required, token ký và đảm bảo Twitter/các nền tảng khác vẫn auto-fallback như trước.",
                "Hỗ trợ ASUMI_PUBLIC_URL; trên Render tự dùng RENDER_EXTERNAL_URL nếu có.",
            ]},
        ],
    },
    {
        "version": "2.8.0",
        "date": "2026-09-25",
        "type": "minor",
        "title": "Asumi: Xác minh bản xem trước & Thống nhất phong cách Tarot",
        "summary": "Asumi là tên sản phẩm mới. Preview proxy được xác minh trên Discord trước khi tính thành công; Tarot dùng một Asumi với nhiều phong cách và chế độ Tự động mặc định.",
        "changes": [
            {"category": "✨ Tên gọi Asumi", "items": [
                "Cập nhật tên hiện tại trong Discord, website, help, Cabin và version tracker; giữ alias cũ để nhận câu hỏi và giữ nguyên tên hạ tầng/lịch sử.",
            ]},
            {"category": "🪝 Bản xem trước mạng xã hội có xác minh", "items": [
                "Chặn thẻ đăng nhập/generic Facebook dù có OG image; xác minh Discord unfurl trong khoảng chờ giới hạn.",
                "Thử proxy tiếp theo khi preview không dùng được; dọn tin nhắn lỗi và chuyển sang fallback yt-dlp nếu cần.",
                "Chỉ ẩn embed gốc và ghi thành công khi đã có bản xem trước dùng được.",
            ]},
            {"category": "🔮 Một Asumi với nhiều phong cách Tarot", "items": [
                "Một nhân vật Asumi với Tự động, Tĩnh, Dịu, Tinh quái; Tự động là mặc định.",
                "Prompt ngắn hơn, bám ngữ cảnh và giữ an toàn; style ID cũ và lịch sử/rating vẫn tương thích.",
            ]},
        ],
    },
    {
        "version": "2.7.6",
        "date": "2026-09-17",
        "type": "bugfix",
        "title": "Sửa Lỗi Mở Modal Đặt Câu Hỏi Tarot & Khôi Phục Thông Báo Cooldown Thân Thiện",
        "summary": "Bản vá nóng cho luồng Tarot: sửa lỗi 400 Bad Request (50035 Invalid Form Body) khi nhấn nút 'Đặt Câu Hỏi' do placeholder vượt 100 ký tự và giá trị câu hỏi cũ vượt max_length; đồng thời khắc phục lỗi toàn bộ thông báo cooldown Slash Command không được gửi thân thiện (chỉ log traceback ERROR) vì handler tree.error vốn được đăng ký sai chỗ trong on_error event nên gần như không bao giờ kích hoạt - nay được đăng ký ngay trong setup_hook.",
        "changes": [
            {
                "category": "🔮 Vá Lỗi Modal Đặt Câu Hỏi Tarot (50035)",
                "items": [
                    "Rút gọn placeholder TextInput câu hỏi từ 106 xuống dưới 100 ký tự, khắc phục lỗi Discord 400 'placeholder: Must be 100 or fewer in length' khi bấm 'Đặt Câu Hỏi'.",
                    "Clamp giá trị câu hỏi/bối cảnh cũ truyền vào modal xuống 500 ký tự đúng max_length, tránh 50035 khi mở lại modal với câu hỏi dài đã nhập từ prefix command."
                ]
            },
            {
                "category": "⏳ Khôi Phục Thông Báo Cooldown Thân Thiện",
                "items": [
                    "Chuyển đăng ký tree.error handler và interaction_check từ on_error event (gần như không bao giờ chạy) sang setup_hook để kích hoạt ngay khi bot khởi động.",
                    "Khi người dùng gọi /tarot hoặc các Slash Command khác trong 30s cooldown, bot giờ phản hồi tin nhắn ephemeral thân thiện '⏳ Bạn đang thao tác quá nhanh...' thay vì ném CommandOnCooldown lên default handler gây traceback ERROR trong log.",
                    "Lỗi cooldown sau khi defer dùng followup.send; lỗi hệ thống khác vẫn được log đầy đủ stack trace nhưng không crash interaction."
                ]
            }
        ]
    },
    {
        "version": "2.7.5",
        "date": "2026-09-17",
        "type": "bugfix",
        "title": "Củng Cố Luồng Tarot/Embed, Giới Hạn AI Bất Đồng Bộ & Bảo Mật Khởi Động",
        "summary": "Bản vá độ tin cậy toàn diện: sửa parser JSON Tarot làm lộ is_valid=false và JSON rác ra embed; bổ sung System Instruction an toàn chống prompt-injection cho Tarot; chuyển toàn bộ gọi AI (Tarot/Summary/Cabin) sang client bất đồng bộ có timeout hủy được request nền kèm semaphore giới hạn đồng thời; sửa split_text đảm bảo mọi chunk không vượt giới hạn Discord; bảo vệ luồng tương tác Tarot chống double-flip, dọn AI task mồ côi, giới hạn embed 6000 ký tự kèm attachment đầy đủ; vá các lỗ hổng Embed pipeline (spoiler, giới hạn nội dung, media download bound, chặn fallback khi bị block); giới hạn MapReduce đồng thời và đồng bộ QA evaluator với chế độ short; yêu cầu cấu hình ADMIN_PASSWORD/FLASK_SECRET_KEY bắt buộc khi khởi động; cảnh báo phân kỳ dữ liệu khi DB rớt về Local.",
        "changes": [
            {
                "category": "🔮 Tarot AI & Luồng Tương Tác",
                "items": [
                    "Viết lại parser JSON đa tầng bằng json.JSONDecoder.raw_decode: sửa lỗi câu hỏi bị từ chối (is_valid=false) trở lại thành hợp lệ khi JSON lỗi, chặn JSON rác lọt ra embed và chữ None lọt vào bài giải.",
                    "Bổ sung TAROT_SYSTEM_INSTRUCTION chèn vào cả 3 config AI: chống prompt-injection từ câu hỏi/@mention, cấm tuyên bố tương lai/suy nghĩ người khác như sự thật, khung xử lý khủng hoảng và ranh giới Yes/No.",
                    "Chống double-flip: asyncio.Lock + cờ _has_completed cho TarotFlipView, chặn hoàn tất/save history 2 lần khi bấm nút song song.",
                    "AI task lifecycle qua TarotManager (create/cancel/await): hủy task mồ côi khi gửi bài thất bại, khi flip lỗi giữa chừng, khi timeout và khi cog unload.",
                    "Followup hỏi thêm chỉ tiêu tốn lượt khi submit modal thành công (trước đây mở modal là mất lượt).",
                    "build_reading_payload giới hạn aggregate 6000 ký tự Discord: đọc quá dài được giữ nguyên trong attachment tarot_reading.txt."
                ]
            },
            {
                "category": "🧵 Client AI Bất Đồng Bộ & Giới Hạn Đồng Thời",
                "items": [
                    "bounded_ai_generate() mới trong core/ai.py dùng AsyncClient của google-genai: asyncio.wait_for giờ hủy thật request nền thay vì chỉ bỏ thread chạy tiếp ngốn quota.",
                    "Chuyển Tarot (reading + followup), Summary (Map/Reduce/QA) và Cabin sang đường đi bất đồng bộ, loại bỏ to_thread cho các lệnh gọi model.",
                    "Semaphore toàn cục 6 request AI đồng thời cho summary/cabin dùng chung, MapReduce chunk giới hạn 3 song song chống 429.",
                    "Xác minh end-to-end qua SDK google-genai thật với GenerateContentConfig/Candidate object chuẩn."
                ]
            },
            {
                "category": "🪝 Embed Pipeline (Social Media)",
                "items": [
                    "Spoiler an toàn: link is_spoiler luôn che media, cắt chuỗi spoiler an toàn markdown (không đứt || giữa chừng), tên author clamp 256 ký tự tránh Discord 400.",
                    "Lifecycle: cog_unload cancel + await toàn bộ worker task; delete origin xóa mọi preview liên quan (trước đây chỉ xóa 1); preview content clamp 2000 ký tự, allowed_mentions none chống @everyone ping qua display name.",
                    "Media download giới hạn 10MB (tôn trọng filesize_limit guild), kiểm tra Content-Type spoiler thay vì mặc định .jpg.",
                    "Chặn NSFW block rơi xuống Tier 1/2 (trước đây nội dung bị chặn vẫn được post qua proxy); yt-dlp chỉ upload MP4 progressive, không còn manifest HLS/DASH thành file mp4 hỏng."
                ]
            },
            {
                "category": "📝 Summary & Cabin",
                "items": [
                    "MapReduce: chunk thất bại được đánh dấu rõ 'KHÔNG HOÀN THÀNH' thay vì trộn lỗi hệ thống vào nội dung tổng hợp như dữ liệu thật.",
                    "QA Evaluator mode-aware: chế độ short không còn bị trừ điểm theo timeline chi tiết hay ngưỡng 3500 ký tự của chế độ dài.",
                    "Cabin: prompt đóng khung PARODY hư cấu, cấm tuyên bố đời tư/thiên hướng/sức khỏe người khác như sự thật, bổ sung nhánh xử lý lịch sự cho câu nhạy cảm."
                ]
            },
            {
                "category": "🔐 Cấu Hình & Cơ Sở Dữ Liệu",
                "items": [
                    "Bắt buộc ADMIN_PASSWORD & FLASK_SECRET_KEY khi khởi động (raise RuntimeError nếu thiếu); loại bỏ mật khẩu admin fallback cứng trong web/app.py.",
                    "Cảnh báo phân kỳ dữ liệu khi Turso Cloud lỗi và bot rớt về Local SQLite: log timestamp giờ VN + nhắc merge thủ công nếu muốn giữ dữ liệu local."
                ]
            }
        ]
    },
    {
        "version": "2.7.4",
        "date": "2026-09-09",
        "type": "bugfix",
        "title": "Khôi Phục Lệnh Cabin & Khóa An Toàn Khởi Tạo Bot (Command Sync Safety Lock)",
        "summary": "Khắc phục triệt để lỗi mất lệnh /cabin và các lệnh Tarot trước đó: khôi phục 100% các Slash Commands và Prefix Commands của Dịch Cabin; thiết lập cơ chế Khóa An Toàn (Safety Lock) tự động hủy tree.sync() nếu có extension bị lỗi hoặc thiếu lệnh cốt lõi nhằm ngăn Discord xóa sạch lệnh; bổ sung cơ chế thử lại (retry) khi nạp extension và lệnh quản trị /sync (.m sync) để đồng bộ tức thì cho từng máy chủ.",
        "changes": [
            {
                "category": "🎙️ Khôi Phục Toàn Bộ Lệnh Cabin",
                "items": [
                    "Khôi phục đầy đủ Slash Commands: /cabin (bật/tắt toggle, khiên bảo vệ, đè quyền) và /cabinstop (dừng nhanh phiên cabin).",
                    "Khôi phục Prefix Commands: .m cabin, .m cabin stop, .m cabin list, .m cabinstop, .m cabinlist.",
                    "Tích hợp trơn tru toàn bộ các lệnh với Debounce Batch Engine và sửa định dạng phản hồi micro chuẩn 🎙️ Dịch cabin:.",
                    "Khởi động task cleanup an toàn trong cog_load() và bắt lỗi Client not initialised trong before_loop."
                ]
            },
            {
                "category": "🛡️ Nâng Cấp Hệ Thống Khởi Tạo Bot (Bot Init & Sync Safety Lock)",
                "items": [
                    "Thiết lập EXPECTED_CORE_SLASH_COMMANDS bảo vệ các lệnh quan trọng: help, mhelp, version, setstatus, tomtat, autoembed, tarot, cabin, cabinstop.",
                    "Safety Lock: Tự động hủy lệnh tree.sync() toàn cầu nếu phát hiện bất kỳ extension nào nạp lỗi hoặc thiếu lệnh cốt lõi, bảo vệ tuyệt đối lệnh trên Discord không bị xóa sạch.",
                    "Thêm cơ chế tự động thử lại (Retry Backoff) tối đa 2 lần khi nạp extension, chống lỗi timeout mạng tạm thời với Turso Cloud.",
                    "Bổ sung lệnh Quản trị viên /sync và .m sync [guild/global]: Hỗ trợ đồng bộ tức thì 0 giây cho máy chủ (guild_only) để khôi phục hoặc test lệnh ngay lập tức không cần chờ Discord cache 1 tiếng."
                ]
            }
        ]
    },
    {
        "version": "2.7.3",
        "date": "2026-09-09",
        "type": "bugfix",
        "title": "Debounce Batch Engine cho Dịch Cabin - Gom Tin Nhắn Chống RPM",
        "summary": "Tối ưu hóa hạ tầng Dịch Cabin: thay thế cơ chế xử lý tức thời từng tin nhắn bằng Debounce Batch Engine - tự động chờ 3 giây để gom các tin nhắn liên tiếp của nạn nhân lại, rồi gọi AI 1 lần duy nhất với prompt tổng hợp. Kết quả: giảm đáng kể số lần gọi API (chống Rate Limit RPM), câu dịch coherent hơn khi nạn nhân nhắn nhiều tin liên tiếp, và reply luôn vào tin nhắn cuối cùng trong batch.",
        "changes": [
            {
                "category": "🚀 Cabin Debounce Batch Engine (Anti-RPM)",
                "items": [
                    "Thay thế cơ chế in-flight guard (block ngay) bằng debounce buffer: mỗi tin nhắn của nạn nhân được đẩy vào buffer, tạo asyncio.Task delay 3s.",
                    "Nếu nạn nhân gửi thêm tin trong 3s, task cũ bị hủy và task mới được tạo với toàn bộ tin nhắn đã gom - tránh N lần gọi API cho N tin nhắn liên tiếp.",
                    "Sau 3s debounce, gọi generate_cabin_interpretation_batch() với tất cả texts trong batch, AI tổng hợp thành 1-2 câu dịch coherent rồi reply vào tin nhắn cuối cùng.",
                    "Tự động fallback về generate_cabin_interpretation() đơn lẻ khi chỉ có 1 tin nhắn trong batch (zero overhead cho trường hợp thông thường).",
                    "Cooldown check-only khi nhận tin (update=False), chỉ lock cooldown thật sự ngay trước khi gọi AI để tránh double-lock khi nhiều tin được buffer."
                ]
            },
            {
                "category": "🧹 Dọn Dẹp & Tối Ưu Cog",
                "items": [
                    "Thêm cog_unload cleanup: tự động hủy tất cả debounce tasks đang pending khi unload cog, tránh task leak.",
                    "Context filter thông minh: loại bỏ tất cả tin nhắn trong batch khỏi context window để AI không bị lặp lại chính nội dung cần dịch.",
                ]
            }
        ]
    },
    {
        "version": "2.7.2",
        "date": "2026-09-09",
        "type": "bugfix",
        "title": "Sửa Lỗi ActivityLogger, Chống Cụt Câu Dịch Cabin & Tối Ưu Context Tập Trung Nạn Nhân",
        "summary": "Bản vá khẩn cấp cho tính năng Dịch Cabin: Sửa lỗi AttributeError do gọi sai tên hàm ActivityLogger, mở rộng quota token từ 350 lên 1200 và bổ sung cơ chế kiểm duyệt câu dở dang chống cụt chữ; đồng thời thu hẹp ngữ cảnh lịch sử xuống 4 tin nhắn gần nhất và cấu trúc lại prompt tập trung 100% vào nội dung câu nói của nạn nhân; tối ưu cơ chế cooldown chỉ kích hoạt khi dịch thành công.",
        "changes": [
            {
                "category": "🎙️ Tinh Chỉnh & Vá Lỗi Dịch Cabin AI",
                "items": [
                    "Sửa lỗi AttributeError: 'ActivityLogger' object has no attribute 'log_activity' bằng cách chuẩn hóa gọi activity_logger.log(...) và thêm bí danh log_activity.",
                    "Khắc phục triệt để lỗi cụt câu: Nâng max_output_tokens từ 350 lên 1200 để các model tư duy (Gemini 3.7 / 3.8 Flash) không bị cạn token, bổ sung hàm is_incomplete_sentence và chặn FinishReason.MAX_TOKENS để tự động fallback khi câu bị cắt ngang.",
                    "Thu hẹp ngữ cảnh & Trọng tâm nạn nhân: Giảm CONTEXT_MAX_MESSAGES từ 25 xuống 4 tin nhắn và thời gian từ 30 xuống 5 phút; tái cấu trúc prompt ưu tiên 100% vào tin nhắn nạn nhân vừa gửi, tránh bị loãng chủ đề cũ của kênh.",
                    "Tối ưu Cooldown: Cooldown 8s chỉ kích hoạt sau khi bot đã dịch và reply thành công; tự động reset cooldown ngay nếu lượt gọi AI gặp lỗi hoặc timeout để không làm trôi tin nhắn tiếp theo của nạn nhân."
                ]
            }
        ]
    },
    {
        "version": "2.7.1",
        "date": "2026-09-09",
        "type": "bugfix",
        "title": "Nâng Cấp Diễn Giải Tarot (Nữ Tính Hóa Celeste, Rẽ Nhánh Quyết Định, Celtic Cross 10 Lá) & Đè Quyền Dịch Cabin",
        "summary": "Nâng cấp chất lượng luận giải Tarot: tinh chỉnh Persona Celeste đong đầy nữ tính, dịu dàng, thấu cảm; triển khai cơ chế rẽ nhánh quyết định ('Nếu là A thì vầy, nếu là B thì vầy, lựa chọn là ở bạn') triệt tiêu câu trả lời lấp lửng; nâng cấp trải bài Yes/No với tiêu chí chốt hạ 2 chiều và trải bài Celtic Cross 10 lá với dòng chảy câu chuyện sâu sắc kèm cái kết dứt khoát. Đồng thời bổ sung cơ chế đè quyền phiên dịch cabin (takeover) và tự động reset cooldown.",
        "changes": [
            {
                "category": "🔮 Nâng Cấp Toàn Diện Cơ Chế Diễn Giải Tarot",
                "items": [
                    "Tinh chỉnh Persona Celeste (healer): Xưng hô thân thương ('bạn thương', 'người bạn của mình'), giọng văn nữ tính, đằm thắm, giàu hình ảnh thơ mộng xoa dịu tâm hồn nhưng thông tuệ chỉ lối sáng tỏ.",
                    "Triệt tiêu câu trả lời ba phải: Thay vì buông câu lười biếng 'tùy bạn tự quyết', bot vẽ ra bản đồ rẽ nhánh định hướng 2 chiều: nếu chọn Hướng A thì hành động ra sao và chuẩn bị tinh thần cho điều gì; nếu chọn Hướng B thì xử lý thế nào và nhận lại sự bình yên ra sao. Quyền lựa chọn cuối cùng luôn ở người hỏi nhưng với lộ trình vững vàng.",
                    "Trải bài Yes/No: Tích hợp mục ⚡ TIÊU CHÍ CHỐT HẠ phân tích điều kiện chọn CÓ/LÀM vs KHÔNG/BỎ kèm quy tắc tự vấn 1 phút dứt khoát.",
                    "Trải bài Celtic Cross (10 lá): Tái cấu trúc thành 5 phần lớn (>4.000 ký tự) gồm 📖 DÒNG CHẢY CÂU CHUYỆN kết nối các trục lá bài và 🏆 CÁI KẾT CUỐI CÙNG & ĐÍCH ĐẾN minh bạch, dứt khoát.",
                    "Trải bài Choices / Two Paths: So sánh đối đầu trực diện cái giá và thành quả giữa 2 phương án.",
                    "Dynamic Timeout: Tự động tăng thời gian chờ lên 26 giây cho các trải bài lớn (>= 5 lá) giúp AI hoàn thành bài giải sâu sắc."
                ]
            },
            {
                "category": "🔄 Cơ Chế Đè Quyền Dịch Cabin & Reset Cooldown",
                "items": [
                    "Cho phép người thứ ba (C) đè quyền phiên cabin của người trước (A) trên cùng nạn nhân (B).",
                    "Tự động gỡ phiên của A ra (giải phóng slot cho A) và chuyển nạn nhân sang danh nghĩa đang bị C troll (tính vào hạn ngạch của C).",
                    "Reset bộ đếm thời gian chờ dịch của nạn nhân B về 0 ngay lập tức để người mới C có thể troll ngay tin nhắn đầu tiên.",
                    "Phản hồi thông báo Embed đè quyền trực quan (🎙️ ĐÃ ĐÈ QUYỀN DỊCH CABIN!)."
                ]
            }
        ]
    },
    {
        "version": "2.7.0",
        "date": "2026-09-09",
        "type": "minor",
        "title": "Ra Mắt Tính Năng Dịch Cabin Troll AI Trực Tiếp & Chuỗi Fallback 7 Tầng Toàn Hệ Thống",
        "summary": "Bổ sung module Dịch Cabin thời gian thực cực kỳ hài hước: bot đóng vai phiên dịch viên cabin song song, tự động đọc ngữ cảnh 30 phút gần nhất của kênh chat để 'chuyển ngữ' câu nói của người chỉ định sang góc nhìn ngôi thứ nhất châm biếm, bóc trần sự thật ngầm hiểu hoặc bẻ lái bất ngờ. Đồng thời chuẩn hóa chuỗi mô hình dự phòng AI (Fallback Cascade) 7 tầng cho tất cả các tính năng Tarot, Cabin, Tóm tắt tin nhắn và QA Evaluator.",
        "changes": [
            {
                "category": "🎙️ Tính Năng Dịch Cabin Trực Tiếp (/cabin)",
                "items": [
                    "Slash Command duy nhất: /cabin @user [thoi_gian] với cơ chế Toggle thông minh (chưa bật thì bật, đang bật thì tự tắt).",
                    "Hỗ trợ các lệnh tiền tố linh hoạt: .m cabin @user [thời_gian], .m cabinstop, .m cabinlist.",
                    "Định dạng phản hồi trực diện: '🎙️ Dịch cabin: <nội dung bẻ lái>' tự động reply tin nhắn nạn nhân."
                ]
            },
            {
                "category": "🧠 Nắm Bắt Ngữ Cảnh Hội Thoại & Góc Nhìn Ngôi Thứ Nhất",
                "items": [
                    "Tự động quét tối đa 25 tin nhắn trong 30 phút gần nhất của kênh chat để AI nắm bắt chủ đề trò chuyện.",
                    "Người phiên dịch cabin bắt buộc nói thay lời nạn nhân ở ngôi thứ nhất ('Tao/Tôi/Mình/Em'), tự thú nhận sự thật bựa/sĩ diện/lươn lẹo trúng tim đen."
                ]
            },
            {
                "category": "🛡️ Quản Lý Khiên Chống Cabin Độc Quyền Quản Trị & Fair-play",
                "items": [
                    "Giới hạn 1 người chỉ được tạo tối đa 1 phiên cabin tại một thời điểm.",
                    "Quản lý cấp/gỡ Khiên miễn nhiễm độc quyền trên Admin Web Dashboard (/admin), loại bỏ lệnh chat công khai tránh lạm dụng.",
                    "Nút bấm 1-chạm 🛑 Dừng Cabin đính kèm thông báo giúp nạn nhân hoặc Admin giải thoát bất kỳ lúc nào.",
                    "Cooldown 8 giây per-victim và bộ lọc tin nhắn thông minh chống spam flood kênh.",
                    "Lưu trữ phiên bền vững vào Database Turso LibSQL Cloud / SQLite để bảo toàn trạng thái khi bot khởi động lại."
                ]
            },
            {
                "category": "🤖 Chuỗi Fallback 7 Tầng Toàn Hệ Thống (Fallback Cascade Matrix)",
                "items": [
                    "Thứ tự fallback chuẩn hóa đồng bộ cho Tarot, Cabin, Summary và QA Evaluator: 3.8 flash -> 3.7 flash -> 3.6 flash -> 3.5 flash -> 3.5 flash lite -> 3.1 flash lite -> Gemma 4.",
                    "Đưa Gemini 3.8 Flash (gemini-3.8-flash) làm mô hình mặc định cho Tarot, Cabin, Summary và QA.",
                    "Áp dụng cơ chế bắt lỗi và fallback tự động cho Single-Pass, MapReduce Reduce và AI Evaluator."
                ]
            },
            {
                "category": "🖥️ Nâng Cấp Web Console & Showcase Trang Khách",
                "items": [
                    "Tab Quản Trị Dịch Cabin mới trên Web Dashboard: Giám sát Live Sessions, dừng cưỡng chế từ xa và quản lý Khiên bảo vệ.",
                    "Cập nhật hiển thị realtime các model đang hoạt động trên Web Console Overview và Cabin Engine Card.",
                    "Showcase tính năng Dịch Cabin trên Public Landing Page và menu trợ giúp tương tác .m / /help."
                ]
            }
        ]
    },
    {
        "version": "2.6.0",
        "date": "2026-09-04",
        "type": "minor",
        "title": "Tái Cấu Trúc Toàn Diện Web Console: Ra Mắt Trang Khách Công Khai & Phân Quyền Bảng Quản Trị",
        "summary": "Phân chia rõ ranh giới giữa Trang Khách công khai (hiển thị trạng thái realtime, thông số bot, showcase tính năng và nhật ký cập nhật Changelog đầy đủ không cần đăng nhập) và Bảng Quản Trị bảo mật cao cấp dành riêng cho Admin, kết hợp thiết kế thẩm mỹ hiện đại Dark Space & Glassmorphism.",
        "changes": [
            {
                "category": "🌐 Phân Quyền Tuyến Đường & Tách Biệt Vai Trò (Role-Based Routing)",
                "items": [
                    "Trang Khách công khai (/): Bất kỳ ai cũng có thể truy cập mà không bị chặn đăng nhập, hiển thị thông số cơ bản và toàn bộ lịch sử Changelog.",
                    "Trang Quản trị (/admin): Bảo vệ nghiêm ngặt bằng @login_required, tự động chuyển hướng /login?next=/admin nếu chưa có session.",
                    "Phân tách API: Mở công khai /api/public/stats và /api/version; giữ bảo mật tuyệt đối các API quản trị (/api/stats, /api/activities, /api/guilds, /api/tarot/*)."
                ]
            },
            {
                "category": "🎨 Ra Mắt Trang Khách Hiện Đại (Public Guest Landing Page)",
                "items": [
                    "Thiết kế giao diện Dark Space Palette sang trọng kết hợp hiệu ứng Glassmorphism mờ viền, font Outfit & JetBrains Mono.",
                    "Thanh điều hướng Sticky Glass Header với avatar bot, chấm trạng thái live pulse ring, liên kết cuộn mượt và nút Mời Bot / Quản trị.",
                    "Hero Section & Live Quick Stats: 5 thẻ thông số tự động cập nhật realtime mỗi 5 giây (Status, Ping ms, Uptime, Servers, Tiền tố .m).",
                    "Showcase 4 nhóm tính năng cốt lõi: Auto-Embed 9 MXH, Bốc bài Tarot 78 lá, Tóm tắt tin nhắn AI MapReduce và Hạ tầng Cloud 24/7."
                ]
            },
            {
                "category": "📜 Nhật Ký Cập Nhật Trực Quan Cho Cộng Đồng (Public Changelog)",
                "items": [
                    "Hero Release Card nổi bật phiên bản mới nhất kèm ngày phát hành, codename, tóm tắt và danh mục thay đổi có badge phân loại.",
                    "Timeline Accordion tương tác xem lại toàn bộ 28 bản cập nhật trước đó từ v2.5.3 về đến v1.0.0 hoàn toàn công khai."
                ]
            },
            {
                "category": "🛠️ Cải Tiến Trải Nghiệm Bảng Quản Trị & Đăng Nhập",
                "items": [
                    "Bổ sung nút 'Xem Trang Khách' trên header Admin Dashboard để chuyển đổi nhanh giữa 2 giao diện.",
                    "Tự động đồng bộ số hiệu phiên bản động lên header badge và tab badge thay vì chuỗi tĩnh.",
                    "Trang đăng nhập (/login) bổ sung nút quay về Trang Khách và hỗ trợ chuyển hướng thông minh qua tham số next."
                ]
            }
        ]
    },
    {
        "version": "2.5.3",
        "date": "2026-09-04",
        "type": "bugfix",
        "title": "Khắc Phục Lỗi Desync Gỡ Reaction & Kích Hoạt Lại Thông Báo Khi Nhiều Người Thả Trùng Emote",
        "summary": "Tự động gỡ ra thả lại reaction trên tin nhắn gốc khi có thêm người dùng thả cùng loại emote trên Embed Preview nhằm kích hoạt lại thông báo/hiệu ứng cho chủ bài viết, bảo toàn reaction chống desync khi người khác rút emote, và bổ sung khóa đồng bộ asyncio.Lock per-message chống race condition.",
        "changes": [
            {
                "category": "🔔 Kích Hoạt Lại Thông Báo Khi Thả Trùng Emote (Re-trigger)",
                "items": [
                    "Phát hiện trường hợp bot đã thả emote này trước đó trên tin nhắn gốc (khi có người thứ 2+ cùng thả emote đó trên Embed Preview).",
                    "Thực hiện quy trình gỡ emote cũ của bot, nghỉ 0.3s và thả lại ngay lập tức để Discord bắn lại push notification / hiệu ứng nhảy emote cho tác giả tin nhắn gốc."
                ]
            },
            {
                "category": "🛡️ Chống Lỗi Desync Khi Người Dùng Gỡ Reaction (Desync Guard)",
                "items": [
                    "Trước khi gỡ reaction khỏi tin nhắn gốc, bot truy vấn trực tiếp trạng thái Embed Preview từ Discord API để kiểm tra số lượng count còn lại.",
                    "Nếu trên Embed vẫn còn ít nhất 1 người đang thả emote đó (count > 0), bot giữ nguyên reaction trên tin nhắn gốc, tuyệt đối không gỡ nhầm.",
                    "Chỉ gỡ emote khỏi tin nhắn gốc khi toàn bộ người dùng trên Embed đều đã rút sạch emote đó về 0."
                ]
            },
            {
                "category": "🔒 Khóa Đồng Bộ Asyncio Lock Theo Tin Nhắn (Thread-Safety)",
                "items": [
                    "Bổ sung BoundedDict lưu trữ asyncio.Lock độc lập theo từng message_id gốc.",
                    "Đảm bảo các sự kiện thêm/gỡ reaction diễn ra đồng thời trong cùng 1 giây được xếp hàng xử lý tuần tự, loại bỏ hoàn toàn race condition và lỗi nghẽn API Discord."
                ]
            }
        ]
    },
    {
        "version": "2.5.2",
        "date": "2026-09-04",
        "type": "minor",
        "title": "Nhận Thức Đối Tượng Được Tag (@Mentions), Phân Biệt Thành Viên Server & Linh Hoạt Vùng Xám Đùa Vui",
        "summary": "Trích xuất và chuẩn hóa tag/mention trong câu hỏi Tarot; phân biệt rõ người hỏi, bot và người thứ 2 trong server; nới lỏng quy chuẩn cho các câu hỏi trêu đùa/khen ngợi bạn bè lành mạnh (không quá strict) và hướng dẫn AI luận giải năng lượng lá bài về đúng đối tượng.",
        "changes": [
            {
                "category": "🏷️ Phân Tích Thực Thể & Chuẩn Hóa Mentions (<@ID> & @Name)",
                "items": [
                    "Hàm extract_question_mentions_context tự động phân giải Discord raw mentions <@123...> thành @DisplayName để Gemini AI hiểu mượt mà.",
                    "Phân biệt rõ ràng 3 thực thể độc lập: Người yêu cầu bốc bài (user_name), Chính Bot (bot_name), và Thành viên khác trong server (@Member)."
                ]
            },
            {
                "category": "🧠 Bổ Sung Khối Bối Cảnh Đối Tượng Vào Prompt AI",
                "items": [
                    "Chèn phân tích đối tượng và vai trò vào khối THÔNG TIN QUẺ BÀI, thông báo cho Reader biết chính xác người hỏi đang hướng sự chú ý đến ai."
                ]
            },
            {
                "category": "⚖️ Nới Lỏng Quy Chuẩn Vùng Xám & Đùa Vui (Không Quá Strict)",
                "items": [
                    "Bổ sung ngoại lệ vào Nguyên tắc 4: Các câu hỏi trêu đùa, khen ngợi, hỏi vui về bạn bè trong server (như '@Mike có siêu cấp đẹp gái không?') luôn được xem là hợp lệ (is_valid: true), không bị từ chối khắt khe.",
                    "Chỉ từ chối khi thực sự có hành vi soi mói đời tư độc hại hoặc xâm phạm bí mật nhạy cảm giữa các bên thứ ba."
                ]
            },
            {
                "category": "🃏 Định Hướng Luận Giải Đúng Đối Tượng (Nguyên Tắc 7)",
                "items": [
                    "Bổ sung Nguyên tắc 7 vào Prompt: Hướng dẫn AI giải mã năng lượng lá bài về thần thái, vẻ đẹp, phong cách của người được tag mà không nhầm lẫn với Bot.",
                    "Đưa ra lời nhắn nhủ, đối đáp dí dỏm kết nối giữa người hỏi và người bạn được tag theo đúng Persona."
                ]
            },
            {
                "category": "🔄 Tích Hợp Toàn Diện Mọi Luồng Trải Bài",
                "items": [
                    "Đồng bộ truyền context qua Slash/Prefix flow (cog.py), Interactive Launcher View, và Modal hỏi đáp đào sâu bổ sung (tarot_view.py)."
                ]
            }
        ]
    },
    {
        "version": "2.5.1",
        "date": "2026-09-04",
        "type": "bugfix",
        "title": "Tối Ưu Trọng Tâm Luận Giải Tarot, Bám Sát Biểu Tượng Lá Bài & Đồng Bộ Phán Quyết Yes/No",
        "summary": "Khắc phục triệt để tình trạng trả lời lạc đề / văn mẫu chung chung khi người dùng đặt câu hỏi meta/thử tài bot; bắt buộc AI bám sát chủ đề câu hỏi, lái biểu tượng lá bài vào thực tế kèm lời khuyên hành động cụ thể, và đồng bộ tuyệt đối với phán quyết Yes/No.",
        "changes": [
            {
                "category": "🎯 Trả Lời Trực Diện & Xử Lý Câu Hỏi Meta / Thử Tài Bot",
                "items": [
                    "Bổ sung Nguyên tắc 5 vào AI Prompt: Ngăn chặn tuyệt đối việc AI tự suy diễn mọi câu hỏi thành chuyện tình cảm lứa đôi hay văn mẫu chữa lành sáo rỗng.",
                    "Xử lý chuyên biệt cho câu hỏi thử tài bot (như 'Bot có biết bói tarot không?'): Reader tự tin xác nhận vai trò và khả năng giải bài, giải mã lá bài rút được theo đúng ngữ cảnh thử tài và gợi ý người dùng đặt câu hỏi thực tế."
                ]
            },
            {
                "category": "🃏 Biểu Tượng Sát Thực Tế & Lời Khuyên Hành Động Cụ Thể",
                "items": [
                    "Bắt buộc gắn chi tiết, hình ảnh của lá bài vào sự việc của câu hỏi thay vì trích dẫn định nghĩa từ điển lý thuyết chung chung.",
                    "Chuẩn hóa mục Advice thành các bước hành động cụ thể, thực tế (Actionable Steps) mà người hỏi có thể thực hiện ngay."
                ]
            },
            {
                "category": "⚡ Đồng Bộ Tuyệt Đối Phán Quyết Yes / No",
                "items": [
                    "Truyền trực tiếp kết quả phán quyết chính thức (Badge & Mô tả) vào AI Prompt.",
                    "Ràng buộc mục Kết luận và bài giải phải đồng thuận với phán quyết, loại bỏ hoàn toàn mâu thuẫn 'trên CÓ, dưới KHÔNG'."
                ]
            },
            {
                "category": "🎭 Tinh Chỉnh Persona Readers (Orion, Celeste, Jester)",
                "items": [
                    "Bổ sung chỉ dẫn giữ đúng trọng tâm câu hỏi cho cả 3 Persona, đặc biệt là Celeste (dịu dàng nhưng trực diện, không biến mọi chuyện thành sầu muộn)."
                ]
            }
        ]
    },
    {
        "version": "2.5.0",
        "date": "2026-09-04",
        "type": "minor",
        "title": "Bổ Sung Quy Tắc Đạo Đức Tarot & Bảo Vệ Quyền Riêng Tư Của Người Thứ Ba",
        "summary": "Thêm cơ chế kiểm tra tính hợp lệ của câu hỏi trải bài Tarot: Từ chối giải quẻ khi người hỏi bốc bài hỏi thay hoặc soi mói đời tư người thứ ba (như A hỏi chuyện của B và C mà A không liên quan), đồng thời hỗ trợ từ chối theo phong cách từng Persona và vô hiệu hóa phán quyết Yes/No.",
        "changes": [
            {
                "category": "🔮 Quy Chuẩn Đạo Đức & Ranh Giới Trải Bài Tarot",
                "items": [
                    "Bổ sung cờ is_valid vào TarotAIResponseSchema và cập nhật nguyên tắc số 4 trong AI Prompt.",
                    "Cho phép hỏi về người khác NẾU người hỏi là một bên trong mối quan hệ/tình huống đó và cần lời khuyên cho bản thân (ví dụ: 'Người ấy nghĩ gì về tôi?').",
                    "Tuyệt đối từ chối giải quẻ nếu người hỏi bốc bài hỏi thay hoặc tò mò, soi mói đời tư, bí mật của bên thứ ba mà bản thân đứng ngoài (ví dụ: A hỏi chuyện tình cảm, comeout của B và C).",
                    "Cập nhật phản hồi từ chối phù hợp theo 3 Persona: Orion (nghiêm nghị, chuẩn mực), Celeste (dịu dàng, thấu cảm), Jester (cà khịa hài hước tính hóng drama).",
                    "Áp dụng quy tắc đạo đức tương tự cho câu hỏi đào sâu bổ sung (Follow-up Questions)."
                ]
            },
            {
                "category": "⚡ Giao Diện Người Dùng & Phán Quyết Yes / No",
                "items": [
                    "Tự động phát hiện câu hỏi không hợp lệ và cập nhật phán quyết Yes/No thành 🚫 KHÔNG HỢP LỆ (VI PHẠM NGUYÊN TẮC) thay vì hiển thị Có/Không sai lệch.",
                    "Cập nhật Placeholder tại Modal nhập câu hỏi và lưu ý tại Bảng thiết lập trải bài Tarot để hướng dẫn người dùng."
                ]
            }
        ]
    },
    {
        "version": "2.4.15",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Quét Tự Động Dọn Dẹp Embed Mồ Côi Khi Khởi Động & Ghi Log Trực Tiếp Lên Dashboard",
        "summary": "Tự động quét các tin nhắn embed trước đó khi bot khởi động để dọn sạch các embed mồ côi (nếu tin nhắn gốc bị xóa lúc bot offline) đồng thời khôi phục bộ nhớ theo dõi, và đồng bộ mọi sự kiện xóa/hủy embed lên Live Dashboard & Console.",
        "changes": [
            {
                "category": "🧹 Quét Embed Mồ Côi Khi Khởi Động (Startup Orphan Scanner)",
                "items": [
                    "Tự động rà soát lịch sử tin nhắn bot trên các kênh text sau khi khởi động.",
                    "Nếu tin nhắn gốc đã bị xóa mất từ trước (lúc bot offline/redeploy), bot tự động xóa sạch embed mồ côi tương ứng.",
                    "Nếu tin nhắn gốc còn tồn tại, bot nạp lại ánh xạ theo dõi 2 chiều vào cache để tiếp tục đồng bộ xóa trong tương lai."
                ]
            },
            {
                "category": "📊 Đồng Bộ Sự Kiện Xóa Vào Live Dashboard & Console",
                "items": [
                    "Cập nhật mọi hành động hủy task in-flight, thu hồi bản xem trước, và xóa embed vào ActivityLogger (Web Dashboard) và Console logs trong thời gian thực."
                ]
            }
        ]
    },
    {
        "version": "2.4.14",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Xử Lý Triệt Để Trường Hợp User Xóa Tin Nhắn Trong Lúc Bot Chưa Kịp Trả Lời (Zero Orphan Embeds)",
        "summary": "Tự động hủy tác vụ đang xử lý (download/crawl) và chặn gửi embed preview nếu tin nhắn gốc bị người dùng xóa trước khi bot kịp rep, đồng thời bổ sung hỗ trợ xóa hàng loạt (bulk purge).",
        "changes": [
            {
                "category": "🛡️ Đồng Bộ Vòng Đời Tin Nhắn & Hủy Tác Vụ Đang Xử Lý (In-Flight Cancellation)",
                "items": [
                    "Khắc phục hoàn toàn race condition: Nếu người dùng xóa tin nhắn gốc trong lúc bot đang tải video hoặc gọi API, bot lập tức hủy bỏ tác vụ (Task.cancel()), giải phóng tài nguyên và tuyệt đối không gửi embed mồ côi ra kênh chat.",
                    "Kiểm tra guard kép trong _send_embed_preview trước và ngay sau khi gửi để thu hồi ngay lập tức nếu sự kiện xóa xảy ra đồng thời.",
                    "Bổ sung listener on_raw_bulk_message_delete để tự động dọn sạch các embed tương ứng khi tin nhắn bị xóa hàng loạt (purge)."
                ]
            }
        ]
    },
    {
        "version": "2.4.13",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Bảo Toàn Embed Facebed Native & Loại Bỏ Xóa Tin Nhắn Sớm (Zero False Fallback)",
        "summary": "Loại bỏ hoàn toàn bộ đếm thời gian 2.5s tự xóa tin nhắn proxy (vốn là nguyên nhân xóa mất embed của Facebed ngay khi Discord vừa render), giữ nguyên tin nhắn proxy để Discord bung embed mượt mà tương tự RePlay.",
        "changes": [
            {
                "category": "⚡ Khắc Phục Triệt Để Lỗi Xóa Mất Embed Facebed",
                "items": [
                    "Gỡ bỏ cơ chế tự động xóa tin nhắn sau 2.5s (nguyên nhân khiến bot xóa mất embed Facebed đang tải dở của người dùng rồi nhảy fallback thừa).",
                    "Giữ nguyên tin nhắn chứa link Facebed để Discord tự nhiên crawl và hiển thị video player native chuẩn xác 100% giống như bot RePlay.",
                    "Chỉ kích hoạt Tier 2 (yt-dlp) khi proxy thực sự bị lỗi mạng hoặc sập server từ đầu."
                ]
            }
        ]
    },
    {
        "version": "2.4.12",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Chuẩn Hóa Đường Dẫn Facebook watch?v= Tối Ưu Cho Facebed & Làm Sạch Giao Diện Embed",
        "summary": "Chuẩn hóa link Facebook sang định dạng canonical /watch?v=ID (tương tự bot RePlay), dỡ bỏ điều kiện chặn nhầm proxy facebed.com, và tự động ẩn ảnh thumbnail tĩnh khi video MP4 đã được đính kèm để tránh lặp hình ảnh.",
        "changes": [
            {
                "category": "⚡ Chuẩn Hóa Proxy Facebook (Đồng Bộ Chuẩn RePlay)",
                "items": [
                    "Tự động chuyển đổi các link /reel/ID, /videos/ID, watch/?v=ID sang https://facebed.com/watch?v=ID để Discord và Facebed nhận diện chuẩn xác 100%.",
                    "Dỡ bỏ kiểm tra has_image quá nghiêm ngặt trên proxy Facebook, cho phép facebed.com hoạt động bình thường như các bot lớn.",
                    "Giữ nguyên cơ chế Active Unfurl Verification: Nếu Discord bung được embed facebed thì hiển thị native mượt mà; chỉ kích hoạt fallback khi proxy thực sự không render được."
                ]
            },
            {
                "category": "🎨 Tinh Gọn Giao Diện Embed",
                "items": [
                    "Khắc phục lỗi lặp 2 lần hình ảnh: Tự động ẩn ảnh thumbnail tĩnh trong embed khi file video MP4 đã được đính kèm (Discord tự tạo video player native có hình nền)."
                ]
            }
        ]
    },
    {
        "version": "2.4.11",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Tự Động Chọn Định Dạng Video Phù Hợp (<=25MB) & Bổ Sung Thông Báo Fallback",
        "summary": "Tự động thử các định dạng video ứng viên (HD, SD) để đảm bảo file video <= 25MB luôn được tải và phát native có tiếng trên Discord, đồng thời bổ sung thông báo rõ ràng khi xảy ra fallback từ Facebed/Proxy.",
        "changes": [
            {
                "category": "🎬 Trình Phát Video Native & Tự Động Thử Định Dạng (Multi-Candidate)",
                "items": [
                    "Khắc phục tình trạng chỉ hiện ảnh thumbnail khi video HD vượt quá giới hạn 25MB: Hệ thống tự động quét tất cả các định dạng video MP4 (progressive HD/SD) và chọn phiên bản phù hợp (<= 25MB) để đính kèm.",
                    "Đảm bảo 100% video Facebook và các nền tảng khác luôn có video player phát trực tiếp kèm âm thanh trong Discord chat."
                ]
            },
            {
                "category": "🔔 Thông Báo Fallback Trực Quan",
                "items": [
                    "Bổ sung ghi chú thông báo trên header subtext: '-# [Trả lời] Mike • ⚠️ Facebed lỗi, đã tự động fallback' giúp người dùng hiểu rõ lý do kích hoạt chế độ trích xuất trực tiếp.",
                    "Đồng bộ ghi chú footer: 'Facebook • Fallback từ facebed'."
                ]
            }
        ]
    },
    {
        "version": "2.4.10",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Cơ Chế Giám Sát Unfurl Discord, Trích Xuất Facebook Native & Chuẩn Hóa Vòng Đời Presence",
        "summary": "Bổ sung cơ chế Active Unfurl Verification tự động phát hiện và xóa tin nhắn proxy rỗng khi Discord bị 403 CDN để kích hoạt Fallback yt-dlp, trích xuất Facebook trực tiếp qua yt-dlp ở Tier 0, và chuẩn hóa trạng thái Presence cố định kèm cảnh báo lỗi Gateway tự động.",
        "changes": [
            {
                "category": "👑 Cơ Chế Giám Sát Unfurl Discord (Active Unfurl Verification)",
                "items": [
                    "Tự động lắng nghe sự kiện Gateway message_edit sau khi gửi link proxy: Nếu sau 2.5s Discord âm thầm hủy embed (do CDN 403 hoặc lỗi phân giải), bot tự động xóa tin nhắn rỗng và lập tức kích hoạt Fallback Tier 2 (yt-dlp).",
                    "Không bao giờ để lại tin nhắn rác hoặc link trống trong khung chat khi các proxy bên thứ ba bị chập chờn."
                ]
            },
            {
                "category": "⚡ Nâng Cấp Toàn Diện Facebook Embed",
                "items": [
                    "Tích hợp yt-dlp trực tiếp vào Tier 0 (fetch_facebook): Lấy trọn vẹn Tiêu đề, Tác giả, Thumbnail gốc Facebook (không bị 403) và tải đính kèm file video MP4 (<= 25MB) để phát native có tiếng chỉ trong ~3.5s.",
                    "Chuẩn hóa đường dẫn Facebook: Tự động chuyển đổi các link dạng /share/v/ sang /share/r/ theo chuẩn tối ưu của các bot lớn.",
                    "Cập nhật Proxy Validator: Yêu cầu bắt buộc phải có thẻ ảnh poster (og:image) đối với video proxy Facebook, từ chối các proxy cụt media như facebed."
                ]
            },
            {
                "category": "🎭 Chuẩn Hóa Trạng Thái Presence & Vòng Đời Bot",
                "items": [
                    "Loại bỏ danh sách xoay tua các slash command không cần thiết (/tarot, /tomtat), chuẩn hóa trạng thái cố định: Live v2.4.10 | .m help.",
                    "Tự động chuyển sang Updating (Cam 🟡) trước khi tắt / redeploy trên Render/Gunicorn.",
                    "Hệ thống Watchdog chạy nền: Tự động nhảy sang Error (Đỏ 🔴 / DND) khi độ trễ Gateway > 5s hoặc mất kết nối, và tự động khôi phục Xanh 🟢 khi ổn định."
                ]
            }
        ]
    },
    {
        "version": "2.4.9",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Khắc Phục Stream Video TikTok & Bảo Vệ Cache Cooldown Domain",
        "summary": "Gỡ bỏ proxy tiktxk.com bị lỗi Akamai 403 (Image failed to load), ưu tiên tnktok.com (fxTikTok chính thức), đồng thời tinh chỉnh cache domain không kích hoạt cooldown khi timeout trên bài viết đơn lẻ.",
        "changes": [
            {
                "category": "⚡ Tối Ưu Hóa Proxy TikTok & Cache",
                "items": [
                    "Loại bỏ hoàn toàn tiktxk.com khỏi danh sách proxy do dịch vụ đã ngừng duy trì và trả về endpoint video bị lỗi 403 Forbidden.",
                    "Ưu tiên tnktok.com (fxTikTok) và tfxktok.com cho toàn bộ link TikTok để đảm bảo video player native hoạt động 100%.",
                    "Thêm chữ ký nhận diện lỗi tiktxk vào bộ lọc validator để tự động loại bỏ proxy hỏng.",
                    "Bảo vệ cache cooldown: Chỉ cách ly domain khi gặp lỗi máy chủ (502/503) hoặc mất kết nối mạng, tránh ngộ độc cache khi timeout bài viết đơn lẻ."
                ]
            }
        ]
    },
    {
        "version": "2.4.8",
        "date": "2026-09-03",
        "type": "bugfix",
        "title": "Làm Gọn Subtext Embed & Tối Ưu Hóa Proxy Fallback",
        "summary": "Ẩn link proxy trực tiếp vào hyperlink [Xem bài viết gốc], lược bỏ icon reply ↩️ ở subtext, loại bỏ kiểm tra video stream CDN gây lỗi 403, cập nhật danh sách proxy hoạt động ổn định và ngăn ngừa fallback thừa sang yt-dlp.",
        "changes": [
            {
                "category": "🎨 Giao Diện & Trải Nghiệm Embed",
                "items": [
                    "Làm gọn subtext: Chuyển link raw proxy thành link markdown '[Xem bài viết gốc](url)', không để lộ link proxy ra chat.",
                    "Lược bỏ icon reply ↩️, giữ nguyên dòng định dạng subtext siêu nhỏ: -# [Trả lời](jump_url) **Tên** • [Xem bài viết gốc](url).",
                    "Đồng bộ xóa icon reply ↩️ ở cả Tier 0 (API), Tier 1 (Proxy) và Tier 2 (yt-dlp)."
                ]
            },
            {
                "category": "⚡ Tối Ưu Hóa Proxy & Fallback",
                "items": [
                    "Khắc phục lỗi kiểm tra video stream: Gỡ bỏ HTTP GET trực tiếp tới video CDN URL trong validator (nguyên nhân gây HTTP 403 trên Facebook CDN và kích hoạt fallback thừa sang yt-dlp).",
                    "Cập nhật Proxy Domains: Bỏ proxy chết (kktiktok, kkinstagram), ưu tiên các proxy nhanh và ổn định (tiktxk, tfxktok, vxreddit, fixthreads).",
                    "Sửa API fxtwitter: Cho phép API fxtwitter chấp nhận cả tweet dạng văn bản lẫn media mà không bị từ chối.",
                    "Bảo vệ cache domain: Không đưa domain proxy vào blacklist cooldown khi gặp lỗi bài viết 404 hoặc riêng tư.",
                    "Giới hạn yt-dlp Tier 2: Chỉ fallback yt-dlp cho các nền tảng video, giảm timeout từ 30s xuống 15s để tránh treo luồng."
                ]
            }
        ]
    },
    {
        "version": "2.4.7",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Khắc Phục Vòng Đời Gunicorn Worker & Quét Cổng HTTP Render",
        "summary": "Khắc phục triệt để lỗi trang web không truy cập được (No open HTTP ports detected) bằng cách chuyển luồng Discord Bot vào Gunicorn Worker qua post_fork hook và gỡ bỏ việc ghi đè Signal Handlers.",
        "changes": [
            {
                "category": "🛠️ Ổn Định Gunicorn & WSGI Worker",
                "items": [
                    "Sử dụng hook post_fork trong gunicorn.conf.py để kích hoạt Discord Bot thread ngay sau khi Worker process được fork.",
                    "Xóa bỏ eager ensure_bot_started() ở top-level module import của app.py, ngăn bot chạy sai trong Master process.",
                    "Gỡ bỏ việc ghi đè signal.SIGTERM / SIGINT ở cấp độ module, tránh làm Gunicorn Master process bị exit(0) đột ngột.",
                    "Bổ sung 2 endpoint công khai /healthz và /ping (HTTP 200) phục vụ Render Port Scanner & Uptime Monitors."
                ]
            }
        ]
    },
    {
        "version": "2.4.6",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Chuyển Đổi Prefix Mặc Định Sang .m",
        "summary": "Cập nhật tiền tố lệnh mặc định của bot từ $m sang .m (.m, .M) trên toàn bộ hệ thống xử lý, menu tương tác, ví dụ lệnh và trạng thái Presence.",
        "changes": [
            {
                "category": "⚡ Chuyển Đổi Tiền Tố (Prefix Migration)",
                "items": [
                    "Cập nhật BOT_DEFAULT_PREFIXES = ['.m', '.M'] trong core/constants.py và bot_instance.py.",
                    "Đồng bộ toàn bộ chuỗi trạng thái Presence sang dạng: Live v2.4.6 | .m help.",
                    "Cập nhật toàn bộ các menu hướng dẫn /help, overview, tarot, tomtat sang prefix .m."
                ]
            }
        ]
    },
    {
        "version": "2.4.5",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Tinh Chỉnh Danh Xưng Tarot & Cập Nhật Giao Diện Trợ Giúp",
        "summary": "Chuẩn hóa thuật ngữ tính năng Tarot sang 'Bốc bài Tarot chiêm tinh' (lược bỏ chữ AI) trong chuỗi xoay tua trạng thái Presence và menu Help của bot.",
        "changes": [
            {
                "category": "🔮 Tinh Chỉnh Thuật Ngữ Tarot",
                "items": [
                    "Đổi chuỗi trạng thái xoay tua: '🔮 /tarot - Bốc bài Tarot chiêm tinh'.",
                    "Chuẩn hóa tiêu đề và mô tả trong Overview Help Embed & Tarot Help View."
                ]
            }
        ]
    },
    {
        "version": "2.4.4",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Chính Sách Trạng Thái DND Cho Sự Cố & Bảo Trì",
        "summary": "Quy định trạng thái bot khi gặp sự cố, lỗi hoặc bảo trì luôn được chuyển sang chế độ Do Not Disturb (DND - Chấm đỏ) thay vì Offline để đảm bảo người dùng luôn đọc được lý do và tiến độ xử lý.",
        "changes": [
            {
                "category": "🎭 Tinh Chỉnh Presence & Trạng Thái Sự Cố",
                "items": [
                    "Bổ sung hàm set_error() tự động chuyển sang DND kèm lý do chi tiết khi gặp sự cố kỹ thuật.",
                    "Tuyệt đối không chuyển trạng thái bot sang Offline tự động, giữ nguyên dòng Custom Status hiển thị công khai."
                ]
            }
        ]
    },
    {
        "version": "2.4.3",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Khắc Phục Import Config & Thread-Safe Logging Reentrancy",
        "summary": "Sửa lỗi thiếu import config trong app.py và bảo vệ luồng ghi log stdout/stderr chống xung đột Reentrant BufferedWriter trên Python 3.14 Render.",
        "changes": [
            {
                "category": "🛠️ Sửa Lỗi Worker Thread & Logger (HotFix)",
                "items": [
                    "Bổ sung import config vào app.py phục vụ khởi chạy bot.run(config.DISCORD_TOKEN).",
                    "Sử dụng threading.RLock() và cờ reentrancy guard cho LogStreamRedirector chống lỗi RuntimeError: reentrant call inside BufferedWriter."
                ]
            }
        ]
    },
    {
        "version": "2.4.2",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Khắc Phục Lỗi Import Flask & Ổn Định Khởi Động Gunicorn WSGI",
        "summary": "Bổ sung đầy đủ các dependency của Flask vào Web Console, giải quyết triệt để lỗi NameError và đảm bảo tiến trình khởi chạy mượt mà 100% trên Render.",
        "changes": [
            {
                "category": "🛠️ Sửa Lỗi Triển Khai (Deployment BugFix)",
                "items": [
                    "Bổ sung các thành phần Flask (render_template, request, jsonify, redirect, url_for, session, Response) vào web/app.py.",
                    "Đồng bộ tiến trình WSGI Gunicorn với luồng chạy ngầm của Discord Bot Gateway, tự động khởi động không chờ HTTP request."
                ]
            }
        ]
    },
    {
        "version": "2.4.1",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Tối Ưu Embed Threads, Tập Trung Constants & Sửa Hiển Thị Trạng Thái Bot",
        "summary": "Nâng cấp bộ giải mã link Threads.net (vxthreads, shortlinks /t/, /share/), chuyển toàn bộ constants và AI models về core/constants.py và sửa lỗi hiển thị CustomActivity trên Discord.",
        "changes": [
            {
                "category": "👑 Nâng Cấp Threads Embed Toàn Diện",
                "items": [
                    "Hỗ trợ đầy đủ các định dạng liên kết Threads: @user/post/ID, threads.net/t/ID, threads.net/share/post/ID và threads.net/share/ID.",
                    "Tích hợp proxy chính vxthreads.com siêu nhẹ kèm cơ chế fallback fixthreads.seria.moe.",
                    "Tự động chuẩn hóa đường dẫn /share/ sang /t/ tăng tốc độ resolve dữ liệu OpenGraph.",
                    "Mở rộng regex nhận diện ID chứa ký tự gạch ngang (-) và gạch dưới (_)."
                ]
            },
            {
                "category": "📁 Tái Cấu Trúc Centralized Constants (core/constants.py)",
                "items": [
                    "Tập trung toàn bộ cấu hình AI Models (gemini-3.7-flash, gemini-3.5-flash-lite, gemini-3.1-flash-lite) và nhiệt độ generation vào core/constants.py.",
                    "Gom nhóm toàn bộ tham số giới hạn (Limits), cấu hình mặc định nền tảng (PLATFORMS) và danh sách proxy vào core.",
                    "Loại bỏ hoàn toàn phụ thuộc ngược từ core vào features, đảm bảo tính đóng gói kiến trúc chuẩn mực."
                ]
            },
            {
                "category": "🎭 Tinh Chỉnh Giao Diện Trạng Thái (Presence Engine)",
                "items": [
                    "Sửa lỗi không hiện trạng thái do thiếu trường state trong CustomActivity payload của Discord Gateway.",
                    "Tự động khởi chạy bot worker thread ngay khi Gunicorn nạp module (không cần chờ request đầu tiên).",
                    "Đổi text Live sang dạng ngắn gọn: Live v2.4.1 | $m help và loại bỏ emoji bóng tròn màu sắc."
                ]
            }
        ]
    },
    {
        "version": "2.4.0",
        "date": "2026-08-28",
        "type": "minor",
        "title": "Đại Tu Auto-Embed QoL Toàn Diện & Dynamic Presence",
        "summary": "Nâng cấp cơ chế Suppress Embed gốc bảo toàn tin nhắn, Subtext Jump link siêu gọn, Auto-delete đồng bộ, Force Spoiler NSFW, DB Auto-Pruning và Dynamic Presence.",
        "changes": [
            {
                "category": "👑 Auto-Embed 9 Nền Tảng Tinh Gọn",
                "items": [
                    "Bổ sung hỗ trợ đầy đủ 9 mạng xã hội: Facebook, TikTok, Instagram, Twitter/X, Reddit, Threads, Pixiv, Bluesky, Twitch.",
                    "Cơ chế Suppress Embed gốc: Giữ nguyên 100% tin nhắn & tệp đính kèm, bảo toàn tính năng highlight vàng khi reply.",
                    "Subtext Jump Link: Dòng chú thích siêu nhỏ `-# ↩️ [Trả lời Tên](link) • 🔗 [Xem bài viết](url)`, nhấp vào cuộn ngay về tin gốc mà không bị lặp chữ hay double ping.",
                    "Tự động xóa Embed đồng bộ khi người dùng xóa tin nhắn gốc chứa link.",
                    "Force Spoiler & Tự động nhận diện từ khóa nhạy cảm (nsfw, 18+, spoiler, nhạy cảm...) để che mờ khung embed.",
                    "Làm sạch tên người dùng (Sanitize display name), sửa lỗi vỡ format Markdown Link khi tên chứa ký tự đặc biệt hoặc khoảng trắng."
                ]
            },
            {
                "category": "🌐 Web Dashboard & Cloud Database",
                "items": [
                    "Trang Quản trị Web trực quan với Live Console Streaming & Live Activity Logger.",
                    "Unified Database Adapter: Tự động kết nối Turso LibSQL Cloud và fallback an toàn sang Local SQLite.",
                    "Cơ chế Auto-Pruning tự động dọn dẹp log cũ, chống tràn và tiết kiệm 95% quota ghi DB (giữ 2000 console logs, 5000 activities, 90 ngày tarot).",
                    "Hệ thống Dynamic Presence & Status: Cập nhật trạng thái bot linh hoạt qua Web & Discord Slash Command."
                ]
            }
        ]
    },
    {
        "version": "2.3.1",
        "date": "2026-08-28",
        "type": "bugfix",
        "title": "Cải Tiến Parser Markdown & Tích Hợp Đánh Giá Tarot AI",
        "summary": "Bổ sung nút đánh giá cộng đồng (👍/👎), tối ưu hóa prompt AI và tái cấu trúc parser phân tích quẻ bài Tarot.",
        "changes": [
            {
                "category": "🔮 Tarot AI Refinements",
                "items": [
                    "Bổ sung nút đánh giá chất lượng luận giải quẻ bài (👍/👎) lưu trữ bền vững vào cơ sở dữ liệu.",
                    "Modal tương tác hỏi thêm ý nghĩa (Follow-up AI Question Modal) cho phép người dùng đào sâu chi tiết quẻ bài.",
                    "Tái cấu trúc parser markdown cho phản hồi AI (tự động tách riêng Topic, Mood, Summary headline và Content)."
                ]
            }
        ]
    },
    {
        "version": "2.3.0",
        "date": "2026-08-27",
        "type": "minor",
        "title": "Tích Hợp Turso LibSQL Cloud DB, Quản Trị Server & Logging Bền Vững",
        "summary": "Tích hợp Turso LibSQL Cloud, lưu trữ bền vững bot activities & console logs, và hoàn thiện hệ thống phân quyền máy chủ.",
        "changes": [
            {
                "category": "☁️ Cloud Database & Activity Persistence",
                "items": [
                    "Tích hợp Turso LibSQL Cloud Database kết nối an toàn qua HTTPS/WSS.",
                    "Lưu trữ bền vững danh sách tương tác người dùng (bot_activities) và console logs vào Cloud DB.",
                    "Tối ưu hóa vòng đời kết nối async DB Client chống rò rỉ kết nối trên Event Loop."
                ]
            },
            {
                "category": "🛡️ Quản Trị Máy Chủ (Guild Management)",
                "items": [
                    "Bổ sung hệ thống tạm ngừng / mở lại quyền sử dụng bot cho từng Server (Guild Suspension) kèm lý do chi tiết.",
                    "In-memory Cache cho Guild Configs giúp phản hồi tức thì với độ trễ 0ms.",
                    "Xác thực đăng nhập Web Console bằng HMAC SHA-256 an toàn chống timing attack."
                ]
            },
            {
                "category": "🔮 Tarot AI Enhancements",
                "items": [
                    "Bổ sung Mood Tags, Summary Headlines và API xuất dữ liệu đánh giá quẻ bài (/api/tarot/ratings/export)."
                ]
            }
        ]
    },
    {
        "version": "2.2.0",
        "date": "2026-08-25",
        "type": "minor",
        "title": "Tối Ưu Summary Scan, Lọc Thời Gian & Nâng Cấp Logging",
        "summary": "Nâng cấp tính năng tóm tắt kênh chat với bộ lọc thời gian chuyên sâu và hệ thống lưu trữ error logs.",
        "changes": [
            {
                "category": "📝 Summary Engine",
                "items": [
                    "Bổ sung bộ lọc theo ngày cụ thể, khung giờ bắt đầu - kết thúc và message anchor link.",
                    "Hỗ trợ gửi kết quả tóm tắt trực tiếp qua Direct Message (DM) bảo mật.",
                    "Tăng giới hạn quét tin nhắn tới 2500 tin và hỗ trợ tùy chỉnh kích thước MapReduce chunk."
                ]
            },
            {
                "category": "📊 Logging & Debugging",
                "items": [
                    "Lưu trữ error logs tự động và hỗ trợ bộ lọc cấp độ log trên Web Dashboard."
                ]
            }
        ]
    },
    {
        "version": "2.1.0",
        "date": "2026-08-25",
        "type": "minor",
        "title": "Tối Ưu UX/UI Tarot Launcher, Help View & Tinh Giản Kiến Trúc",
        "summary": "Tối ưu hóa giao diện bốc bài Tarot, hỗ trợ Hybrid Commands và tinh giản các module thử nghiệm để đạt hiệu năng cao nhất.",
        "changes": [
            {
                "category": "🔮 Tarot UX & Optimization",
                "items": [
                    "Cải tiến giao diện chọn kiểu trải bài và người giải bài trực quan.",
                    "Cài đặt Cooldown 30s và tính toán quẻ bài dựa trên Cosmic Energy Seed (1h).",
                    "Tinh giản các module thử nghiệm phụ (TTS Voice, Meme Engine) để tập trung tài nguyên vào AI Reasoning và Canvas Image."
                ]
            },
            {
                "category": "💡 Hybrid Commands & Help UI",
                "items": [
                    "Hỗ trợ Hybrid Command linh hoạt giữa Slash Command (/) và Prefix ($m).",
                    "Giao diện HelpView phân loại rõ ràng theo từng tính năng kèm nút đóng tin nhắn."
                ]
            }
        ]
    },
    {
        "version": "2.0.0",
        "date": "2026-08-24",
        "type": "major",
        "title": "Đại Tu Modular Cogs, Ra Mắt Tarot Engine 78 Lá & Multi-Tier Embed Pipeline",
        "summary": "Bước nhảy vọt kiến trúc 2.0: Chuyển đổi mã nguồn sang hệ thống Modular Discord Cogs, ra mắt tính năng bốc bài Tarot Canvas 78 lá, 3 Reader Personas và pipeline link preview đa tầng.",
        "changes": [
            {
                "category": "🔮 Khởi Tạo Tarot Engine 78 Lá Rider-Waite",
                "items": [
                    "Xây dựng bộ bài 78 lá Tarot Rider-Waite hoàn chỉnh.",
                    "Tích hợp thư viện Pillow render hình ảnh trải bài Canvas trực quan độ phân giải cao.",
                    "Ra mắt 3 phong cách Reader AI: Orion (Logic), Celeste (Thấu cảm), Jester (Trào phúng).",
                    "Giao diện lật từng lá bài tương tác trực tiếp với hiệu ứng lật mặt sau (Card-flip view)."
                ]
            },
            {
                "category": "👑 Pipeline Xử Lý Link Đa Tầng (Embed Multi-Tier)",
                "items": [
                    "Pipeline xử lý URL tự động: API Fetcher ➔ Proxy Chain ➔ yt-dlp Fallback.",
                    "Hỗ trợ trích xuất và hiển thị nội dung bình luận của người dùng đi kèm link.",
                    "Bổ sung bộ nhớ đệm Cooldown Cache cho các tên miền proxy gặp sự cố."
                ]
            },
            {
                "category": "📁 Kiến Trúc Modular Cogs & Web Dashboard",
                "items": [
                    "Tái cấu trúc mã nguồn sang các thư mục tính năng độc lập (features/tarot, features/embed, features/summary).",
                    "Ra mắt phiên bản đầu tiên của Web Admin Dashboard phục vụ giám sát và cấu hình."
                ]
            }
        ]
    },
    {
        "version": "1.1.0",
        "date": "2026-08-04",
        "type": "minor",
        "title": "Tự Động Embed MXH Cơ Bản & Chuyển Sang Gemini Flash Lite",
        "summary": "Bổ sung tính năng hiển thị video/ảnh mạng xã hội tự động và tối ưu hóa mô hình AI sang Gemini Flash Lite.",
        "changes": [
            {
                "category": "👑 Auto-Embed Cơ Bản",
                "items": [
                    "Nhận diện liên kết mạng xã hội (Facebook, TikTok, Instagram) và nhúng video tự động.",
                    "Bộ lọc từ khóa nội dung nhạy cảm (NSFW Filter) sơ bộ."
                ]
            },
            {
                "category": "⚡ Nâng Cấp Mô Hình AI",
                "items": [
                    "Chuyển đổi mô hình AI tóm tắt sang Google Gemini Flash Lite giúp tăng tốc độ phản hồi."
                ]
            }
        ]
    },
    {
        "version": "1.0.0",
        "date": "2026-06-13",
        "type": "major",
        "title": "Khởi Tạo Dự Án MikeDaBot, Tóm Tắt Kênh Chat AI & Deploy Gunicorn",
        "summary": "Bản phát hành đầu tiên thiết lập nền tảng Discord Bot đa luồng, thuật toán MapReduce tóm tắt tin nhắn và triển khai Gunicorn Render.",
        "changes": [
            {
                "category": "🚀 Nền Tảng & Triển Khai",
                "items": [
                    "Xây dựng kiến trúc Hybrid chạy song song Discord Bot Gateway và Flask Web Server.",
                    "Thiết lập Gunicorn Single-Worker Threading giải quyết triệt để lỗi 502 Bad Gateway trên Render."
                ]
            },
            {
                "category": "📝 AI Summary Engine (MapReduce)",
                "items": [
                    "Thuật toán MapReduce tóm tắt song song hỗ trợ quét sâu tới 2500 tin nhắn.",
                    "Anti-hallucination guardrails với Temperature=0.1 đảm bảo tính xác thực cao.",
                    "Lệnh tự kiểm thử `/test_tomtat` và báo cáo kiểm thử tự động."
                ]
            }
        ]
    }
]


def get_version_info() -> Dict[str, Any]:
    """Trả về thông tin chi tiết về phiên bản hiện tại."""
    return {
        "version": CURRENT_VERSION,
        "release_date": RELEASE_DATE,
        "codename": CODENAME,
        "total_releases": len(CHANGELOG),
        "latest_patchnote": CHANGELOG[0] if CHANGELOG else None
    }


def get_changelog() -> List[Dict[str, Any]]:
    """Trả về toàn bộ danh sách các bản cập nhật."""
    return CHANGELOG


def build_version_embed(user: Optional[discord.User | discord.Member] = None) -> discord.Embed:
    """Xây dựng Discord Embed hiển thị thông tin phiên bản và patchnote mới nhất."""
    latest = CHANGELOG[0]
    
    badge_type = {
        "major": "🚀 [MAJOR RELEASE]",
        "minor": "✨ [FEATURE UPDATE]",
        "bugfix": "🛠️ [BUG FIX / HOTFIX]"
    }.get(latest.get("type", "minor"), "✨ [UPDATE]")

    embed = discord.Embed(
        title=f"🤖 THÔNG TIN PHIÊN BẢN {BOT_BRAND_NAME.upper()} — v{CURRENT_VERSION}",
        description=(
            f"**{badge_type}**: **{latest['title']}**\n"
            f"📅 **Ngày phát hành:** `{latest['date']}` • **Codename:** *{CODENAME}*\n\n"
            f"*{latest['summary']}*"
        ),
        color=0x7851A9
    )

    for cat in latest.get("changes", []):
        items_text = "\n".join(f"• {item}" for item in cat["items"])
        embed.add_field(
            name=cat["category"],
            value=items_text,
            inline=False
        )

    embed.add_field(
        name="📜 Lịch Sử Các Phiên Bản Trước",
        value="\n".join(
            f"• `v{rel['version']}` ({rel['date']}): **{rel['title']}**"
            for rel in CHANGELOG[1:]
        ) or "*(Không có phiên bản cũ hơn)*",
        inline=False
    )

    if user:
        embed.set_footer(
            text=f"Yêu cầu bởi {user.display_name} • {BOT_BRAND_NAME} Version Tracker",
            icon_url=user.display_avatar.url if user.display_avatar else None
        )
    return embed
