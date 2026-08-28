"""
core/constants.py - Định nghĩa các hằng số, cấu hình mặc định và regex toàn hệ thống.
"""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# ---------------------------------------------------------------------------
# Cấu hình chung cho Bot
# ---------------------------------------------------------------------------
BOT_DEFAULT_PREFIXES = ["$m", "$M"]
DEFAULT_COLOR_PRIMARY = 0x7851A9
DEFAULT_COLOR_SUCCESS = 0x2ECC71
DEFAULT_COLOR_WARNING = 0xF1C40F
DEFAULT_COLOR_ERROR = 0xE74C3C
DEFAULT_COLOR_TAROT = 0x9B59B6

# Database Pruning Limits
MAX_CONSOLE_LOGS_LIMIT = 2000
MAX_BOT_ACTIVITIES_LIMIT = 5000
TAROT_HISTORY_RETENTION_DAYS = 90

# ---------------------------------------------------------------------------
# Cấu hình Mô hình AI (Centralized AI Models & Generations)
# ---------------------------------------------------------------------------
DEFAULT_GEMINI_DATA_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_SUMMARY_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_QA_MODEL = "gemini-3.5-flash-lite"
DEFAULT_GEMINI_TAROT_MODEL = "gemini-3.7-flash"

DEFAULT_TAROT_FALLBACK_MODELS = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-31b-it",
]

DEFAULT_SUMMARY_TEMPERATURE = 0.1
DEFAULT_QA_TEMPERATURE = 0.3
DEFAULT_TAROT_TEMPERATURE = 0.7

# ---------------------------------------------------------------------------
# Giới hạn & Tham số xử lý dữ liệu (Processing Limits)
# ---------------------------------------------------------------------------
DEFAULT_SINGLE_PASS_MSG_LIMIT = 300
DEFAULT_MAPREDUCE_CHUNK_SIZE = 200
DEFAULT_DISCORD_EMBED_CHAR_LIMIT = 3500
MAX_FETCH_MESSAGES_LIMIT = 4000
DEFAULT_COMMAND_COOLDOWN_SECONDS = 30.0
DEFAULT_SCAN_HOURS = 2.0
DEFAULT_SCAN_LIMIT = 150

# ---------------------------------------------------------------------------
# Trích xuất URL từ tin nhắn Discord
# Xử lý URL trong spoiler (||url||) và URL bị suppress (<url>).
# ---------------------------------------------------------------------------
_SPOILER_URL_PATTERN = re.compile(r"\|\|(https?://[^\s|]+)\|\|")
_REGULAR_URL_PATTERN = re.compile(r"(?<!\$)(?<!<)(https?://[^\s>]+)(?!>)")


# ---------------------------------------------------------------------------
# Regex nhận diện URL theo nền tảng
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
            re.compile(r"https?://(?:www\.|old\.)?reddit\.com(/r/[\w]+/comments/[\w]+/[\w]+)/?"),
            re.compile(r"https?://(?:www\.|old\.)?reddit\.com(/r/[\w]+/s/[\w]+)/?"),
            re.compile(r"https?://(?:www\.|old\.)?reddit\.com(/user/[\w]+/comments/[\w]+/[\w]+)/?"),
            re.compile(r"https?://(?:www\.|old\.)?reddit\.com(/r/\w+/comments/\w+\S*)"),
        ],
    },
    "instagram": {
        "name": "Instagram",
        "color": 0xE1306C,
        "icon_url": "https://cdn-icons-png.flaticon.com/512/174/174855.png",
        "footer_text": "Instagram",
        "button_label": "Xem trên Instagram",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.)?instagram\.com/(?:share/(?:p|reels?)/|share/|(?:p|reels?|tv)/)([\w-]+)"),
        ],
    },
    "facebook": {
        "name": "Facebook",
        "color": 0x1877F2,
        "icon_url": "https://cdn-icons-png.flaticon.com/512/124/124010.png",
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
            re.compile(r"https?://(?:www\.)?bsky\.app/profile/([\w.\-]+)/post/([\w]+)/?"),
            re.compile(r"https?://(?:www\.)?bsky\.app/profile/([\w.:]+)/post/([\w]+)"),
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
            re.compile(r"https?://(?:www\.)?(?:m\.)?twitch\.tv/clip/([\w-]+)/?"),
            re.compile(r"https?://clips\.twitch\.tv/([\w-]+)/?"),
            re.compile(r"https?://(?:www\.)?twitch\.tv/\w+/clip/([\w-]+)/?"),
        ],
    },
    "threads": {
        "name": "Threads",
        "color": 0x000000,
        "icon_url": "https://cdn-icons-png.flaticon.com/512/11104/11104255.png",
        "footer_text": "Threads",
        "button_label": "Xem trên Threads",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.)?threads\.(?:net|com)/@([\w.]+)/post/([\w-]+)\S*"),
            re.compile(r"https?://(?:www\.)?threads\.(?:net|com)/t/([\w-]+)\S*"),
            re.compile(r"https?://(?:www\.)?threads\.(?:net|com)/share/(?:post/)?([\w-]+)\S*"),
            re.compile(r"https?://(?:www\.)?threads\.(?:net|com)/post/([\w-]+)\S*"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Proxy Fallback Registry
# ---------------------------------------------------------------------------
PROXY_DOMAINS = {
    "twitter": ["fxtwitter.com", "vxtwitter.com", "fixupx.com"],
    "pixiv": ["phixiv.net"],
    "tiktok": ["vxtiktok.com", "tnktok.com"],
    "reddit": ["rxddit.com", "fxreddit.seria.moe", "vxreddit.com"],
    "instagram": ["vxinstagram.com", "fxig.seria.moe"],
    "facebook": ["facebed.seria.moe", "facebed.com"],
    "bluesky": ["fxbsky.app", "bskx.app"],
    "twitch": ["fxtwitch.seria.moe"],
    "threads": ["vxthreads.com", "fixthreads.seria.moe"],
}


# ---------------------------------------------------------------------------
# Domain gốc theo nền tảng
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


_NSFW_KEYWORD_PATTERN = re.compile(
    r"(?:\b(?:nsfw|18\+|r18|r-18|spoiler|nhạy\s*cảm|sensitive|hentai|ecchi|lewd|porn)\b)",
    re.IGNORECASE,
)


def extract_urls(text: str) -> list[tuple[str, bool]]:
    """Trích xuất URL từ nội dung tin nhắn Discord và phát hiện cờ spoiler/nsfw."""
    has_nsfw_keyword = bool(_NSFW_KEYWORD_PATTERN.search(text))
    spoiler_urls = [(match, True) for match in _SPOILER_URL_PATTERN.findall(text)]
    text_without_spoilers = _SPOILER_URL_PATTERN.sub("", text)
    regular_urls = [(match, has_nsfw_keyword) for match in _REGULAR_URL_PATTERN.findall(text_without_spoilers)]
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
    """Thay thế domain trong URL bằng domain mới, sử dụng urlparse."""
    parsed = urlparse(url)
    if domain_in_url(url, old_domain):
        new_parsed = parsed._replace(netloc=new_domain)
        return urlunparse(new_parsed)
    return url
