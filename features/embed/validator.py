import re
import time
import asyncio
import aiohttp
from urllib.parse import quote, urlparse

from features.embed.constants import (
    PROXY_DOMAINS,
    PLATFORM_ORIGINAL_DOMAINS,
    PROXY_API_ENDPOINTS,
    replace_domain,
    domain_in_url,
)

# Giới hạn số lượng request xác thực đồng thời để tránh rate-limit
_VALIDATION_SEMAPHORE = asyncio.Semaphore(5)

# Regex phát hiện OpenGraph / Twitter Card meta tags trong HTML
_OG_META_PATTERN = re.compile(
    r'<meta\s+[^>]*(?:'
    r'(?:property|name)\s*=\s*["\']?(?:og:(?:image|video|title|description)|twitter:(?:card|image|player|title|description))'
    r')[^>]*>',
    re.IGNORECASE | re.DOTALL,
)

# Regex phát hiện nội dung NSFW / nhạy cảm trong HTML metadata của Proxy
_NSFW_PATTERN = re.compile(
    r'(?:'
    r'name=["\']twitter:creator["\']\s+content=["\']nsfw["\']'
    r'|property=["\']og:rating["\']\s+content=["\'](?:adult|R-?18)["\']'
    r'|property=["\']og:title["\']\s+content=["\'][^"\']*\b(?:nsfw|18\+|r-18|r-18g)\b[^"\']*["\']'
    r'|content=["\'][^"\']*\b(?:nsfw|18\+|r-18|r-18g)\b[^"\']*["\']'
    r')',
    re.IGNORECASE,
)

# Regex phát hiện trang báo lỗi, ngừng hoạt động, bị chặn API hoặc không tìm thấy bài viết
_DEAD_OR_ERROR_PATTERN = re.compile(
    r'(?:'
    r'due to a legal request'
    r'|this service is no longer available'
    r'|service (?:is )?(?:temporarily )?unavailable'
    r'|service has been discontinued'
    r'|has been shut down'
    r'|cease and desist'
    r'|domain seized'
    r'|page not found'
    r'|404 not found'
    r'|video not found'
    r'|post not found'
    r'|content not found'
    r'|media not found'
    r'|user not found'
    r'|could not be found'
    r'|blocked the request'
    r'|actively preventing this service'
    r'|upstream request failed'
    r'|rate limit'
    r'|too many requests'
    r'|challenge_required'
    r'|login_required'
    r'|log in to continue'
    r'|log in to view'
    r'|account is private'
    r'|this post is private'
    r'|this reel is unavailable'
    r'|this content isn\'t available'
    r'|post unavailable'
    r'|media unavailable'
    r'|failed to fetch'
    r'|failed to load'
    r'|failed to extract'
    r'|could not fetch'
    r'|something went wrong'
    r'|an error occurred'
    r'|unable to fetch'
    r'|error fetching'
    r'|cannot retrieve'
    r'|bad gateway'
    r'|gateway timeout'
    r'|502 bad gateway'
    r'|504 gateway time-out'
    r'|503 service unavailable'
    r'|tiktxk'
    r'|cannot read properties of undefined'
    r')',
    re.IGNORECASE,
)

# Tên/tiêu đề mặc định rỗng của các dịch vụ proxy hoặc nền tảng gốc
_GENERIC_SERVICE_NAMES = {
    "instagram", "facebook", "tiktok", "twitter", "x", "reddit",
    "threads", "bluesky", "twitch", "pixiv", "facebed", "rxddit",
    "fix instagram embeds", "vxthreads", "fxig", "fxtwitter",
    "vxtwitter", "fixupx", "kktiktok", "tiktxk", "vxreddit", "fxreddit",
}

# Các thuộc tính meta media OpenGraph / Twitter Card
_MEDIA_META_KEYS = [
    "og:video", "og:video:url", "og:video:secure_url",
    "twitter:player", "twitter:player:stream",
    "og:image", "og:image:url", "og:image:secure_url",
    "twitter:image", "twitter:image:src",
]

# Kích thước tối đa đọc từ response (256KB) để đảm bảo không bỏ sót thẻ meta
_MAX_READ_BYTES = 262144

# Timeout cho mỗi request xác thực đơn lẻ (3.5s tổng, 1.5s kết nối để fail-fast khi gặp proxy treo)
_VALIDATE_TIMEOUT = aiohttp.ClientTimeout(total=3.5, connect=1.5)

# Cache tạm thời cho các domain proxy đang bị lỗi kết nối/502/down (TTL 30 giây)
_FAILED_DOMAINS_CACHE: dict[str, float] = {}
_FAILED_DOMAIN_TTL = 30.0  # 30 giây


def _mark_domain_failed(domain: str) -> None:
    """Đánh dấu domain tạm thời bị lỗi server/mạng để cooldown."""
    if domain:
        _FAILED_DOMAINS_CACHE[domain] = time.monotonic() + _FAILED_DOMAIN_TTL


def _extract_meta_tags(html: str) -> dict[str, str]:
    """Trích xuất tất cả các thẻ meta (property/name -> content) từ HTML."""
    tags = {}
    for meta_match in re.finditer(r'<meta\s+([^>]+)>', html, re.IGNORECASE):
        attrs_str = meta_match.group(1)
        prop_match = re.search(r'(?:property|name)\s*=\s*["\']?([^"\'\s>]+)', attrs_str, re.IGNORECASE)
        content_match = re.search(r'content\s*=\s*["\']([^"\']*)["\']', attrs_str, re.IGNORECASE)
        if not content_match:
            content_match = re.search(r'content\s*=\s*([^\s>]+)', attrs_str, re.IGNORECASE)
        if prop_match and content_match:
            prop_name = prop_match.group(1).strip().lower()
            content_val = content_match.group(1).strip()
            tags[prop_name] = content_val
    return tags


def build_proxy_url(original_url: str, platform_key: str, proxy_domain: str) -> str | None:
    """Thay thế domain gốc trong URL bằng proxy domain."""
    original_domains = PLATFORM_ORIGINAL_DOMAINS.get(platform_key, [])
    if not original_domains:
        return None

    for orig_domain in original_domains:
        if domain_in_url(original_url, orig_domain):
            res_url = replace_domain(original_url, orig_domain, proxy_domain)
            if platform_key == "threads" and "vxthreads" in proxy_domain:
                # vxthreads.com xử lý đường dẫn dạng /t/ hoặc /@user/post/ tốt nhất
                res_url = re.sub(r"/share/(?:post/)?", "/t/", res_url)
            elif platform_key == "facebook":
                # Chuẩn hóa các định dạng Facebook sang chuẩn tối ưu của facebed (giống RePlay và EmbedFixer)
                reel_match = re.search(r"/(?:reel|videos)/(\d+)", res_url)
                if reel_match:
                    res_url = f"https://{proxy_domain}/watch?v={reel_match.group(1)}"
                elif re.search(r"[?&]v=(\d+)", res_url):
                    v_id = re.search(r"[?&]v=(\d+)", res_url).group(1)
                    res_url = f"https://{proxy_domain}/watch?v={v_id}"
                elif "/share/v/" in res_url:
                    res_url = re.sub(r"/share/v/", "/share/r/", res_url)
            return res_url

    return None


def _resolve_api_url(proxy_domain: str, original_url: str) -> str | None:
    """Tạo URL API từ template, thay thế placeholder bằng dữ liệu từ URL gốc."""
    api_config = PROXY_API_ENDPOINTS.get(proxy_domain)
    if not api_config:
        return None

    template = api_config["template"]
    parsed = urlparse(original_url)
    path_segment = parsed.path.lstrip("/")

    api_url = template.replace("{url}", quote(original_url, safe=""))
    api_url = api_url.replace("{path}", path_segment)
    return api_url


def _check_media_in_json(data: dict, dotpath: str) -> bool:
    """Kiểm tra sự tồn tại của media trong JSON response theo dot notation path."""
    current = data
    for key in dotpath.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return False
        if current is None:
            return False

    if isinstance(current, (dict, list, str)):
        return bool(current)
    return current is not None


async def validate_via_api(
    session: aiohttp.ClientSession,
    original_url: str,
    proxy_domain: str,
) -> tuple[bool, bool]:
    """Xác thực proxy bằng JSON API (nếu có). Trả về (is_valid, is_nsfw)."""
    api_url = _resolve_api_url(proxy_domain, original_url)
    if not api_url:
        return False, False

    api_config = PROXY_API_ENDPOINTS[proxy_domain]
    media_path = api_config["media_check"]

    try:
        async with session.get(
            api_url,
            timeout=_VALIDATE_TIMEOUT,
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                print(
                    f"[ProxyValidator] API trả về HTTP {resp.status}: {api_url}",
                    flush=True,
                )
                return False, False

            data = await resp.json(content_type=None)
            if _check_media_in_json(data, media_path):
                is_nsfw = False
                if "fxtwitter" in proxy_domain:
                    tweet = data.get("tweet", {})
                    is_nsfw = bool(tweet.get("possibly_sensitive") or tweet.get("nsfw"))

                return True, is_nsfw

            print(
                f"[ProxyValidator] API không chứa media ({media_path}): {api_url}",
                flush=True,
            )
            return False, False

    except asyncio.TimeoutError:
        print(
            f"[ProxyValidator] API hết thời gian chờ: {api_url}",
            flush=True,
        )
        return False, False
    except aiohttp.ClientConnectorError as e:
        print(
            f"[ProxyValidator] API không kết nối được (lỗi mạng/DNS): {api_url} - {e}",
            flush=True,
        )
        _mark_domain_failed(proxy_domain)
        return False, False
    except aiohttp.ClientError as e:
        print(
            f"[ProxyValidator] API lỗi client: {api_url} - {e}",
            flush=True,
        )
        return False, False
    except ValueError as e:
        print(
            f"[ProxyValidator] API dữ liệu JSON lỗi: {api_url} - {e}",
            flush=True,
        )
        return False, False


async def validate_via_og_metadata(
    session: aiohttp.ClientSession,
    proxy_url: str,
    platform_key: str = "",
    proxy_domain: str = "",
) -> tuple[bool, bool]:
    """Xác thực proxy URL bằng cách kiểm tra OpenGraph/Twitter Card metadata. Trả về (is_valid, is_nsfw)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discord.app)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,video/*,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        async with session.get(
            proxy_url,
            timeout=_VALIDATE_TIMEOUT,
            headers=headers,
            allow_redirects=True,
            max_redirects=5,
        ) as resp:
            if resp.status not in (200, 206):
                print(
                    f"[ProxyValidator] Proxy trả về HTTP {resp.status}: {proxy_url}",
                    flush=True,
                )
                if resp.status in (500, 502, 503, 504):
                    _mark_domain_failed(proxy_domain)
                return False, False

            # Kiểm tra nếu proxy bị chuyển hướng ngược về trang đăng nhập của nền tảng gốc
            final_url_str = str(resp.url).lower()
            if any(login_path in final_url_str for login_path in [
                "/login", "/accounts/login", "/checkpoint", "/challenge",
                "facebook.com/login", "instagram.com/accounts/login"
            ]):
                print(
                    f"[ProxyValidator] Proxy bị chuyển hướng tới trang đăng nhập: {resp.url}",
                    flush=True,
                )
                return False, False

            content_type = resp.headers.get("Content-Type", "").lower()
            if any(ct in content_type for ct in ["video/", "image/", "audio/"]):
                return True, False

            content = await resp.content.read(_MAX_READ_BYTES)
            html_text = content.decode("utf-8", errors="ignore")

            # Kiểm tra nếu trang chứa thông báo gỡ bỏ / ngừng dịch vụ / chặn truy cập
            if _DEAD_OR_ERROR_PATTERN.search(html_text):
                print(
                    f"[ProxyValidator] Proxy trả về thông báo lỗi/ngừng dịch vụ: {proxy_url}",
                    flush=True,
                )
                return False, False

            # Trích xuất toàn bộ thẻ meta property/name -> content
            meta_tags = _extract_meta_tags(html_text)

            # 1. Kiểm tra sự tồn tại của media thực tế (ảnh, video, audio, player)
            has_media = False
            has_image = False
            has_video = False
            for mk in _MEDIA_META_KEYS:
                val = meta_tags.get(mk)
                if val:
                    val_lower = val.lower()
                    if val_lower not in ("", "#") and not val_lower.endswith(("/favicon.ico", "/favicon.png", "logo.png")):
                        has_media = True
                        if any(ik in mk for ik in ["image", "thumbnail"]):
                            has_image = True
                        if any(vk in mk for vk in ["video", "player"]):
                            has_video = True

            is_nsfw = bool(_NSFW_PATTERN.search(html_text))
            if has_media:
                return True, is_nsfw

            # Với các nền tảng video/hình ảnh bắt buộc (TikTok, Pixiv, Twitch), nếu không có media thì coi như thất bại
            if platform_key in ("tiktok", "pixiv", "twitch"):
                print(
                    f"[ProxyValidator] Không tìm thấy media hợp lệ cho nền tảng video {platform_key}: {proxy_url}",
                    flush=True,
                )
                return False, False

            # 2. Kiểm tra nội dung text phong phú (cho bài viết text-only như Reddit/Threads/Twitter/Bluesky)
            desc = meta_tags.get("og:description") or meta_tags.get("twitter:description") or ""
            title = meta_tags.get("og:title") or meta_tags.get("twitter:title") or ""
            combined_text = f"{title} {desc}".strip()

            # Lọc bỏ nếu nội dung chỉ chứa emoji/số liệu tương tác (VD: "❤️ 76.4k 💬 497") hoặc tên dịch vụ
            cleaned_text = re.sub(r'[\d\s.,kmbKMB❤️💬🔁👍🔥\-_/|]+', '', combined_text)
            if len(cleaned_text) < 4:
                print(
                    f"[ProxyValidator] Nội dung text không đủ chi tiết/chỉ chứa số liệu: {proxy_url}",
                    flush=True,
                )
                return False, False

            if combined_text.lower() not in _GENERIC_SERVICE_NAMES and not _DEAD_OR_ERROR_PATTERN.search(combined_text):
                return True, is_nsfw

            print(
                f"[ProxyValidator] Không tìm thấy media hoặc nội dung OG hợp lệ: {proxy_url}",
                flush=True,
            )
            return False, False

    except asyncio.TimeoutError:
        print(
            f"[ProxyValidator] Hết thời gian chờ ({_VALIDATE_TIMEOUT.total}s): {proxy_url}",
            flush=True,
        )
        return False, False
    except aiohttp.ClientConnectorError as e:
        print(
            f"[ProxyValidator] Proxy không kết nối được (lỗi mạng/DNS): {proxy_url} - {e}",
            flush=True,
        )
        _mark_domain_failed(proxy_domain)
        return False, False
    except aiohttp.ClientError as e:
        print(
            f"[ProxyValidator] Proxy lỗi client: {proxy_url} - {e}",
            flush=True,
        )
        return False, False
    except Exception as e:
        print(
            f"[ProxyValidator] Proxy tạm thời không phản hồi: {proxy_url} - {e}",
            flush=True,
        )
        return False, False


async def find_valid_proxy(
    session: aiohttp.ClientSession,
    original_url: str,
    platform_key: str,
    guild_proxy_domains: list[str] | None = None,
) -> tuple[str | None, bool]:
    """Thực hiện Chain of Responsibility: thử từng proxy domain theo thứ tự ưu tiên. Trả về (proxy_url, is_nsfw)."""
    if guild_proxy_domains is not None:
        proxy_domains = guild_proxy_domains
    else:
        proxy_domains = PROXY_DOMAINS.get(platform_key, [])

    if not proxy_domains:
        print(
            f"[ProxyValidator] Không có proxy nào được cấu hình cho nền tảng '{platform_key}'",
            flush=True,
        )
        return None, False

    now = time.monotonic()
    for i, domain in enumerate(proxy_domains, start=1):
        if domain in _FAILED_DOMAINS_CACHE:
            if now < _FAILED_DOMAINS_CACHE[domain]:
                print(
                    f"[ProxyValidator] Bỏ qua proxy {domain} (đang tạm nghỉ cooldown sau lỗi)",
                    flush=True,
                )
                continue
            else:
                _FAILED_DOMAINS_CACHE.pop(domain, None)

        proxy_url = build_proxy_url(original_url, platform_key, domain)
        if not proxy_url:
            print(
                f"[ProxyValidator] Không thể viết lại URL cho domain '{domain}' "
                f"(nền tảng: {platform_key})",
                flush=True,
            )
            continue

        print(
            f"[ProxyValidator] Thử proxy {i}/{len(proxy_domains)}: {domain} "
            f"(nền tảng: {platform_key})",
            flush=True,
        )

        async with _VALIDATION_SEMAPHORE:
            is_valid = False
            is_nsfw = False

            if domain in PROXY_API_ENDPOINTS:
                is_valid, is_nsfw = await validate_via_api(session, original_url, domain)
                if is_valid:
                    print(
                        f"[ProxyValidator] Xác thực API thành công: {domain} "
                        f"(nền tảng: {platform_key}, NSFW={is_nsfw})",
                        flush=True,
                    )
                    return proxy_url, is_nsfw

            is_valid, is_nsfw = await validate_via_og_metadata(
                session, proxy_url, platform_key=platform_key, proxy_domain=domain
            )

        if is_valid:
            print(
                f"[ProxyValidator] Proxy hợp lệ (OG metadata): {domain} "
                f"(nền tảng: {platform_key}, NSFW={is_nsfw})",
                flush=True,
            )
            return proxy_url, is_nsfw

        print(
            f"[ProxyValidator] Proxy không thỏa mãn điều kiện bài viết: {domain} (nền tảng: {platform_key})",
            flush=True,
        )

    print(
        f"[ProxyValidator] Tất cả proxy đã thất bại cho nền tảng '{platform_key}': "
        f"{original_url}",
        flush=True,
    )
    return None, False
