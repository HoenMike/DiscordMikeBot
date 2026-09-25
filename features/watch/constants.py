"""
features/watch/constants.py - Constants and UI strings for Watch engine.
"""

# Color aesthetic for Watch embeds (Vibrant sapphire blue)
WATCH_EMBED_COLOR = 0x3B82F6

# Cadence presets (id, hours, label, description)
CADENCE_PRESETS = [
    ("6h", 6, "Nhanh (6h)", "Kiểm tra mỗi 6 giờ"),
    ("24h", 24, "Hàng ngày (24h)", "Kiểm tra mỗi 24 giờ (mặc định)"),
    ("72h", 72, "Thư thả (72h)", "Kiểm tra mỗi 3 ngày"),
    ("168h", 168, "Hàng tuần (168h)", "Kiểm tra mỗi 7 ngày"),
]

# Supported cadence hours
VALID_CADENCE_HOURS = {6, 24, 72, 168}

# Validation limits
TITLE_MAX_LEN = 100
QUERY_MAX_LEN = 200
CONDITION_MAX_LEN = 500

# Results & retention
MAX_SEARCH_RESULTS = 10
MAX_STORED_RESULTS_PER_WATCH = 200
MAX_NOTIFICATION_SOURCES = 3

# Friendly user messages
MSG_NOT_CONFIGURED = "🔭 **Watch chưa thể tìm kiếm Web vì Brave Search chưa được cấu hình.**\n*(Quản trị viên cần đặt biến `BRAVE_SEARCH_API_KEY` trong file cấu hình bot.)*"
MSG_BUDGET_EXHAUSTED = "⚠️ **Hạn ngạch tìm kiếm Web tháng này đã đạt giới hạn.** Watch sẽ tiếp tục được giữ nguyên trạng thái và tự động kiểm tra lại khi bước sang tháng mới."
MSG_LIMIT_USER_REACHED = "⛔ **Bạn đã đạt giới hạn tối đa ({max_active}) Watch đang hoạt động!** Hãy xóa hoặc tạm dừng Watch cũ trước khi tạo thêm."
MSG_LIMIT_GLOBAL_REACHED = "⛔ **Hệ thống đã đạt giới hạn tối đa ({max_global}) Watch toàn cầu.** Vui lòng liên hệ Quản trị viên bot để nâng quota."
