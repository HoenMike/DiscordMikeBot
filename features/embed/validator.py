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
_VALIDATION_SEMAPHORE = asyncio.Semaphore(3)

# Regex phát hiện OpenGraph / Twitter Card meta tags trong HTML
_OG_META_PATTERN = re.compile(
    r'<meta\s+[^>]*(?:'
    r'property\s*=\s*["\']og:(?:image|video)["\']'
    r'|name\s*=\s*["\']twitter:(?:card|image|player)["\']'
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

# Kích thước tối đa đọc từ response (64KB) để đảm bảo không bỏ sót thẻ meta
_MAX_READ_BYTES = 65536

# Timeout cho mỗi request xác thực đơn lẻ
_VALIDATE_TIMEOUT = aiohttp.ClientTimeout(total=12)

# Cache tạm thời cho các domain proxy đang bị lỗi kết nối/502/down (TTL 30 giây)
_FAILED_DOMAINS_CACHE: dict[str, float] = {}
_FAILED_DOMAIN_TTL = 30.0  # 30 giây


def build_proxy_url(original_url: str, platform_key: str, proxy_domain: str) -> str | None:
    """Thay thế domain gốc trong URL bằng proxy domain."""
    original_domains = PLATFORM_ORIGINAL_DOMAINS.get(platform_key, [])
    if not original_domains:
        return None

    for orig_domain in original_domains:
        if domain_in_url(original_url, orig_domain):
            return replace_domain(original_url, orig_domain, proxy_domain)

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
                elif "vxtiktok" in proxy_domain:
                    video_data = data.get("data", {})
                    is_nsfw = bool(video_data.get("is_nsfw"))

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
    except (aiohttp.ClientError, ValueError) as e:
        print(
            f"[ProxyValidator] API lỗi kết nối: {api_url} - {e}",
            flush=True,
        )
        return False, False


async def validate_via_og_metadata(
    session: aiohttp.ClientSession,
    proxy_url: str,
) -> tuple[bool, bool]:
    """Xác thực proxy URL bằng cách kiểm tra OpenGraph/Twitter Card metadata. Trả về (is_valid, is_nsfw)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discord.app)",
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
                return False, False

            content = await resp.content.read(_MAX_READ_BYTES)
            html_text = content.decode("utf-8", errors="ignore")

            if _OG_META_PATTERN.search(html_text):
                is_nsfw = bool(_NSFW_PATTERN.search(html_text))
                return True, is_nsfw

            print(
                f"[ProxyValidator] Không tìm thấy OG metadata: {proxy_url}",
                flush=True,
            )
            return False, False

    except asyncio.TimeoutError:
        print(
            f"[ProxyValidator] Hết thời gian chờ: {proxy_url}",
            flush=True,
        )
        return False, False
    except aiohttp.ClientError as e:
        print(
            f"[ProxyValidator] Lỗi kết nối: {proxy_url} - {e}",
            flush=True,
        )
        return False, False
    except Exception as e:
        print(
            f"[ProxyValidator] Lỗi không xác định: {proxy_url} - {e}",
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

            is_valid, is_nsfw = await validate_via_og_metadata(session, proxy_url)

        if is_valid:
            print(
                f"[ProxyValidator] Proxy hợp lệ (OG metadata): {domain} "
                f"(nền tảng: {platform_key}, NSFW={is_nsfw})",
                flush=True,
            )
            return proxy_url, is_nsfw

        _FAILED_DOMAINS_CACHE[domain] = time.monotonic() + _FAILED_DOMAIN_TTL
        print(
            f"[ProxyValidator] Proxy thất bại: {domain} (nền tảng: {platform_key})",
            flush=True,
        )

    print(
        f"[ProxyValidator] Tất cả proxy đã thất bại cho nền tảng '{platform_key}': "
        f"{original_url}",
        flush=True,
    )
    return None, False
