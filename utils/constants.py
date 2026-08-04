import re

PLATFORMS = {
    "twitter": {
        "name": "Twitter / X",
        "color": 0x000000,
        "icon_url": "https://abs.twimg.com/icons/apple-touch-icon-192x192.png",
        "footer_text": "Twitter / X",
        "api_base": "https://api.fxtwitter.com",
        "patterns": [
            re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/(\w+)/status/(\d+)\S*"),
        ],
    },
    "reddit": {
        "name": "Reddit",
        "color": 0xFF4500,
        "icon_url": "https://www.redditstatic.com/desktop2x/img/favicon/android-icon-192x192.png",
        "footer_text": "Reddit",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.)?reddit\.com(/r/\w+/comments/\w+\S*)"),
        ],
    },
    "tiktok": {
        "name": "TikTok",
        "color": 0x010101,
        "icon_url": "https://sf-tb-sg.ibytedtos.com/obj/eden-sg/uhtyvueh7nulogpoguhm/tiktok-icon2.png",
        "footer_text": "TikTok",
        "api_base": "https://api.vxtiktok.com",
        "patterns": [
            re.compile(r"https?://(?:www\.)?tiktok\.com/@[\w.]+/video/(\d+)\S*"),
            re.compile(r"https?://(?:vm|vt)\.tiktok\.com/([\w]+)\S*"),
        ],
    },
    "instagram": {
        "name": "Instagram",
        "color": 0xE1306C,
        "icon_url": "https://static.cdninstagram.com/rsrc.php/v3/yR/r/lam-fZmwmvn.png",
        "footer_text": "Instagram",
        "api_base": "https://api.ddinstagram.com",
        "patterns": [
            re.compile(r"https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([\w-]+)\S*"),
        ],
    },
    "facebook": {
        "name": "Facebook",
        "color": 0x1877F2,
        "icon_url": "https://static.xx.fbcdn.net/rsrc.php/yD/r/d4ZBER7gFRe.ico",
        "footer_text": "Facebook",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.)?facebook\.com/\S+/(?:posts|videos)/\S+"),
            re.compile(r"https?://fb\.watch/[\w]+"),
        ],
    },
    "bluesky": {
        "name": "Bluesky",
        "color": 0x0085FF,
        "icon_url": "https://bsky.app/static/apple-touch-icon.png",
        "footer_text": "Bluesky",
        "api_base": "https://public.api.bsky.app",
        "patterns": [
            re.compile(r"https?://bsky\.app/profile/([\w.:]+)/post/([\w]+)"),
        ],
    },
    "twitch": {
        "name": "Twitch",
        "color": 0x9146FF,
        "icon_url": "https://static.twitchcdn.net/assets/favicon-32-e29e246c157142c94346.png",
        "footer_text": "Twitch",
        "api_base": None,
        "patterns": [
            re.compile(r"https?://(?:www\.)?twitch\.tv/\w+/clip/([\w-]+)\S*"),
            re.compile(r"https?://clips\.twitch\.tv/([\w-]+)\S*"),
        ],
    },
    "pixiv": {
        "name": "Pixiv",
        "color": 0x0096FA,
        "icon_url": "https://www.pixiv.net/favicon.ico",
        "footer_text": "Pixiv",
        "api_base": "https://phixiv.net",
        "patterns": [
            re.compile(r"https?://(?:www\.)?pixiv\.net/(?:\w+/)?artworks/(\d+)"),
        ],
    },
}

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
        "description": "Ẩn embed mặc định của Discord sau khi tạo embed tùy chỉnh",
    },
}


def format_count(n: int | None) -> str:
    if n is None:
        return "N/A"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
