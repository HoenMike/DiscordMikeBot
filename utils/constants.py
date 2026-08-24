import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


# ---------------------------------------------------------------------------
# Trích xuất URL từ tin nhắn Discord
# Xử lý URL trong spoiler (||url||) và URL bị suppress (<url>).
# Trích dẫn từ seriaati/embed-fixer utils/misc.py
# ---------------------------------------------------------------------------
_SPOILER_URL_PATTERN = re.compile(r"\|\|(https?://[^\s|]+)\|\|")
_REGULAR_URL_PATTERN = re.compile(r"(?<!\$)(?<!<)(https?://[^\s>]+)(?!>)")


# ---------------------------------------------------------------------------
# Regex nhận diện URL theo nền tảng
# Trích xuất từ seriaati/embed-fixer fixes.py (Website patterns).
# Mỗi nền tảng có một hoặc nhiều pattern để bắt chính xác URL hợp lệ.
# ---------------------------------------------------------------------------
PLATFORMS = {
    "twitter": {
        "name": "Twitter / X",
        "color": 0x000000,
        "icon_url": "https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        "footer_text": "Twitter / X",
        "button_label": "Xem bản gốc trên X",
        "api_base": "https://api.fxtwitter.com",
        "patterns": [
            re.compile(r"https://(www\.)?twitter\.com/[a-zA-Z0-9_]+/status/\d+(/photo|video/\d+)?/?"),
            re.compile(r"https://(www\.)?x\.com/[a-zA-Z0-9_]+/status/\d+(/photo|video/\d+)?/?"),
            re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/(\w+)/status/(\d+)\S*"),
        ],
    },
    "pixiv": {
        "name": "Pixiv",
        "color": 0x0096FA,
        "icon_url": "https://www.pixiv.net/favicon.ico",
        "footer_text": "Pixiv",
        "button_label": "Xem trên Pixiv",
        "api_base": "https://phixiv.net",
        "patterns": [
            re.compile(r"https://(www\.)?pixiv\.net(/[a-zA-Z]+)?/artworks/(\d+)/?"),
            re.compile(r"https?://(?:www\.)?pixiv\.net/(?:\w+/)?artworks/(\d+)"),
        ],
    },
    "tiktok": {
        "name": "TikTok",
        "color": 0x010101,
        "icon_url": "https://sf-tb-sg.ibytedtos.com/obj/eden-sg/uhtyvueh7nulogpoguhm/tiktok-icon2.png",
        "footer_text": "TikTok",
        "button_label": "Xem trên TikTok",
        "api_base": "https://api.vxtiktok.com",
        "patterns": [
            re.compile(r"https://(www\.)?tiktok\.com/(t/\w+|@[\w.]+/video/(\d+))/?"),
            re.compile(r"https://vm\.tiktok\.com/([\w]+)/?"),
            re.compile(r"https://vt\.tiktok\.com/([\w]+)/?"),
            re.compile(r"https?://(?:www\.)?tiktok\.com/@[\w.]+/video/(\d+)\S*"),
            re.compile(r"https?://(?:vm|vt)\.tiktok\.com/([\w]+)\S*"),
        ],
    },
    "reddit": {
        "name": "Reddit",
        "color": 0xFF4500,
        "icon_url": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png",
        "footer_text": "Reddit",
        "button_label": "Xem trên Reddit",
        "api_base": None,
        "patterns": [
            re.compile(r"https://(www\.|old\.)?reddit\.com(/r/[\w]+/comments/[\w]+/[\w]+)/?"),
            re.compile(r"https://(www\.|old\.)?reddit\.com(/r/[\w]+/s/[\w]+)/?"),
            re.compile(r"https://(www\.|old\.)?reddit\.com(/user/[\w]+/comments/[\w]+/[\w]+)/?"),
            re.compile(r"https?://(?:www\.)?reddit\.com(/r/\w+/comments/\w+\S*)"),
        ],
    },
    "instagram": {
        "name": "Instagram",
        "color": 0xE1306C,
        "icon_url": "https://static.cdninstagram.com/rsrc.php/v3/yR/r/lam-fZmwmvn.png",
        "footer_text": "Instagram",
        "button_label": "Xem trên Instagram",
        "api_base": "https://api.ddinstagram.com",
        "patterns": [
            re.compile(r"https://(www\.)?instagram\.com/share/([\w-]+)/?"),
            re.compile(r"https://(www\.)?instagram\.com/(?:p|reels?)/([\w-]+)/?"),
            re.compile(r"https://(www\.)?instagram\.com/share/(?:p|reels?)/([\w-]+)/?"),
            re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([\w-]+)\S*"),
        ],
    },
    "facebook": {
        "name": "Facebook",
        "color": 0x1877F2,
        "icon_url": "https://static.xx.fbcdn.net/rsrc.php/yD/r/d4ZBER7gFRe.ico",
        "footer_text": "Facebook",
        "button_label": "Xem trên Facebook",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/share/(?:(?:p|r|v)/)?[\w]+/?"),
            re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/(?:reel|reels)/\d+/?"),
            re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/watch/?\?(?:[\w=&]+)?v=\d+"),
            re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/[^/\s]+/(?:posts|videos|photos)/[^/\s]+/?"),
            re.compile(r"https?://(?:www\.|m\.|web\.)?facebook\.com/(?:story|photo|permalink)\.php\?[^\s]+"),
            re.compile(r"https?://(?:www\.)?fb\.watch/[\w-]+/?"),
        ],
    },
    "bluesky": {
        "name": "Bluesky",
        "color": 0x0085FF,
        "icon_url": "https://bsky.app/static/apple-touch-icon.png",
        "footer_text": "Bluesky",
        "button_label": "Xem trên Bluesky",
        "api_base": "https://public.api.bsky.app",
        "patterns": [
            re.compile(r"https://(www\.)?bsky\.app/profile/([\w.\-]+)/post/([\w]+)/?"),
            re.compile(r"https?://bsky\.app/profile/([\w.:]+)/post/([\w]+)"),
        ],
    },
    "twitch": {
        "name": "Twitch",
        "color": 0x9146FF,
        "icon_url": "https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png",
        "footer_text": "Twitch",
        "button_label": "Xem trên Twitch",
        "api_base": None,
        "patterns": [
            re.compile(r"https://m\.twitch\.tv/clip/([\w-]+)/?"),
            re.compile(r"https://clips\.twitch\.tv/([\w-]+)/?"),
            re.compile(r"https://(www\.)?twitch\.tv/\w+/clip/([\w-]+)/?"),
        ],
    },
    "threads": {
        "name": "Threads",
        "color": 0x000000,
        "icon_url": "https://static.cdninstagram.com/rsrc.php/v3/yS/r/ajlEU-wEDyo.png",
        "footer_text": "Threads",
        "button_label": "Xem trên Threads",
        "api_base": None,
        "patterns": [
            re.compile(r"https://(www\.)?threads\.(?:net|com)/@([\w.]+)/post/([\w]+)/?"),
            re.compile(r"https://(www\.)?threads\.(?:net|com)/share/([\w]+)/?"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Proxy Fallback Registry
# Danh sách proxy domain theo thứ tự ưu tiên giảm dần cho mỗi nền tảng.
# Chuỗi fallback được duyệt tuần tự: proxy đầu tiên hợp lệ sẽ được sử dụng.
# ---------------------------------------------------------------------------
PROXY_DOMAINS = {
    "twitter": ["fxtwitter.com", "vxtwitter.com", "fixupx.com"],
    "pixiv": ["phixiv.net"],
    "tiktok": ["vxtiktok.com", "tnktok.com", "kktiktok.com"],
    "reddit": ["rxddit.com", "fxreddit.seria.moe", "vxreddit.com"],
    "instagram": ["ddinstagram.com", "eeinstagram.com", "oginstagram.com"],
    "facebook": ["facebed.seria.moe", "fxfb.seria.moe"],
    "bluesky": ["bskx.app", "fxbsky.app"],
    "twitch": ["fxtwitch.seria.moe"],
    "threads": ["fixthreads.seria.moe", "vxthreads.net"],
}


# ---------------------------------------------------------------------------
# Domain gốc theo nền tảng
# Dùng để xác định domain nào cần được thay thế khi viết lại URL sang proxy.
# ---------------------------------------------------------------------------
PLATFORM_ORIGINAL_DOMAINS = {
    "twitter": ["twitter.com", "x.com"],
    "pixiv": ["pixiv.net"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"],
    "reddit": ["reddit.com"],
    "instagram": ["instagram.com"],
    "facebook": ["facebook.com", "fb.watch", "m.facebook.com", "web.facebook.com"],
    "bluesky": ["bsky.app"],
    "twitch": ["clips.twitch.tv", "m.twitch.tv", "twitch.tv"],
    "threads": ["threads.net", "threads.com"],
}


# ---------------------------------------------------------------------------
# JSON API endpoints cho các proxy hỗ trợ xác thực qua API
# Key = proxy domain, value = dict chứa thông tin API.
#   "template": URL template. Hỗ trợ placeholder {url} (URL gốc đã encode).
#   "media_check": đường dẫn JSON để kiểm tra media (dùng dot notation).
# ---------------------------------------------------------------------------
PROXY_API_ENDPOINTS = {
    "fxtwitter.com": {
        "template": "https://api.fxtwitter.com/{path}",
        "media_check": "tweet.media",
    },
    "vxtiktok.com": {
        "template": "https://api.vxtiktok.com/api/v1/fetch?url={url}",
        "media_check": "data",
    },
}


# ---------------------------------------------------------------------------
# Query params cần giữ lại khi làm sạch URL
# ---------------------------------------------------------------------------
KEEP_QUERY_PARAMS = {}


# ---------------------------------------------------------------------------
# Cấu hình mặc định cho server
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "platforms_enabled": {
        "twitter": True,
        "reddit": True,
        "tiktok": True,
        "instagram": True,
        "facebook": True,
        "bluesky": True,
        "twitch": True,
        "pixiv": True,
        "threads": True,
    },
    "nsfw_mode": "spoiler",
    "auto_embed_enabled": True,
    "suppress_original_embed": True,
}

CONFIG_KEYS = {
    "nsfw_mode": {
        "type": "choice",
        "choices": ["block", "spoiler", "allow"],
        "description": "Chế độ xử lý nội dung NSFW",
    },
    "auto_embed_enabled": {
        "type": "bool",
        "description": "Tự động tạo embed khi phát hiện link mạng xã hội",
    },
    "suppress_original_embed": {
        "type": "bool",
        "description": "Ẩn embed mặc định của Discord sau khi tạo embed tuỳ chỉnh",
    },
}


# ---------------------------------------------------------------------------
# Hàm tiện ích -- URL và hiển thị
# ---------------------------------------------------------------------------

def format_count(n: int | None) -> str:
    """Định dạng số lượng cho hiển thị gọn (VD: 1500 -> 1.5K)."""
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def extract_urls(text: str) -> list[tuple[str, bool]]:
    """Trích xuất URL từ nội dung tin nhắn Discord.

    Xử lý cả URL trong spoiler (||url||) và URL thường.
    Bỏ qua URL bị suppress (<url>) và URL sau ký tự tiền tệ ($).
    Trả về danh sách các tuple (url, is_spoiler).
    """
    spoiler_urls = [(match, True) for match in _SPOILER_URL_PATTERN.findall(text)]

    text_without_spoilers = _SPOILER_URL_PATTERN.sub("", text)
    regular_urls = [(match, False) for match in _REGULAR_URL_PATTERN.findall(text_without_spoilers)]

    return spoiler_urls + regular_urls


def domain_in_url(url: str, domain: str) -> bool:
    """Kiểm tra xem URL có thuộc domain cho trước không (bao gồm subdomain)."""
    parsed = urlparse(url)
    return parsed.netloc == domain or parsed.netloc.endswith(f".{domain}")


def remove_query_params(url: str) -> str:
    """Loại bỏ tracking query params, giữ lại các params cần thiết."""
    parsed = urlparse(url)

    query = ""
    for domain, keep in KEEP_QUERY_PARAMS.items():
        if domain_in_url(url, domain):
            query = urlencode([(k, v) for k, v in parse_qsl(parsed.query) if k in keep])
            break

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        query,
        parsed.fragment,
    ))


def replace_domain(url: str, old_domain: str, new_domain: str) -> str:
    """Thay thế domain trong URL bằng domain mới, sử dụng urlparse.

    Trả về URL đã viết lại nếu domain khớp, ngược lại trả về URL gốc.
    """
    parsed = urlparse(url)
    if domain_in_url(url, old_domain):
        new_parsed = parsed._replace(netloc=new_domain)
        return urlunparse(new_parsed)
    return url


def sanitize_username(display_name: str) -> str:
    """Thay thế 'discord' trong tên hiển thị để tránh API từ chối webhook.

    Discord API từ chối webhook message khi username chứa từ 'discord'
    (không phân biệt hoa thường). Thay thế bằng ký tự tương tự về hình thức
    (U+0257, Latin small letter d with hook) để giữ nguyên giao diện.
    """
    if not display_name:
        return "User"
    sanitized = re.sub(r"(?i)discord", "discor\u0257", display_name)
    sanitized = sanitized.strip()
    if not sanitized:
        return "User"
    return sanitized[:80]
