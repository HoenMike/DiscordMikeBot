"""
core/version.py - Quản lý phiên bản (Semantic Versioning) và Nhật ký phát hành (Patchnotes / Changelog).

Quy tắc phiên bản: Major.Minor.BugFix (Ví dụ: 2.4.1)
- Major: Đại tu kiến trúc hoặc thay đổi nền tảng lớn (1.x.x -> 2.0.0)
- Minor: Bổ sung tính năng mới hoặc nâng cấp module lớn (2.0.0 -> 2.1.0)
- BugFix: Sửa lỗi / Hotfix / Tinh chỉnh cho phiên bản hiện tại (2.4.0 -> 2.4.1)
"""

from typing import Dict, List, Any, Optional
import discord

CURRENT_VERSION = "2.5.1"
RELEASE_DATE = "2026-09-04"
CODENAME = "Tarot Direct Focus & Grounded Symbolism & Yes/No Sync"

# Lịch sử chi tiết các phiên bản phát hành được đồng bộ trực tiếp từ Git Commit History (Mới nhất nằm ở đầu)
CHANGELOG: List[Dict[str, Any]] = [
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
        title=f"🤖 THÔNG TIN PHIÊN BẢN MIKEBOT — v{CURRENT_VERSION}",
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
            text=f"Yêu cầu bởi {user.display_name} • MikeDaBot Version Tracker",
            icon_url=user.display_avatar.url if user.display_avatar else None
        )
    return embed
