import re
import asyncio
import aiohttp
from urllib.parse import quote, urlparse

from utils.constants import (
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

# Kích thước tối đa đọc từ response (16KB) để giảm tải băng thông
_MAX_READ_BYTES = 16384

# Timeout cho mỗi request xác thực đơn lẻ
_VALIDATE_TIMEOUT = aiohttp.ClientTimeout(total=8)


# ---------------------------------------------------------------------------
# Xây dựng proxy URL từ URL gốc
# ---------------------------------------------------------------------------

def build_proxy_url(original_url: str, platform_key: str, proxy_domain: str) -> str | None:
    """Thay thế domain gốc trong URL bằng proxy domain.

    Sử dụng replace_domain() (urlparse-based) thay vì thay thế chuỗi thủ công.
    Xử lý các trường hợp đặc biệt: subdomain (www., old., m., vm., vt.),
    và domain có path riêng (clips.twitch.tv).

    Trả về URL đã được viết lại, hoặc None nếu không xác định được domain gốc.
    """
    original_domains = PLATFORM_ORIGINAL_DOMAINS.get(platform_key, [])
    if not original_domains:
        return None

    # Thử thay thế lần lượt từng domain gốc (ưu tiên domain cụ thể hơn trước)
    for orig_domain in original_domains:
        if domain_in_url(original_url, orig_domain):
            return replace_domain(original_url, orig_domain, proxy_domain)

    return None


# ---------------------------------------------------------------------------
# Bước 1: Xác thực qua JSON API (nếu proxy có API)
# ---------------------------------------------------------------------------

def _resolve_api_url(proxy_domain: str, original_url: str) -> str | None:
    """Tạo URL API từ template, thay thế placeholder bằng dữ liệu từ URL gốc.

    Hỗ trợ hai loại placeholder:
      - {url}: URL gốc đã được URL-encode
      - {path}: phần path của URL gốc (bỏ dấu / đầu)
    """
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
    """Kiểm tra sự tồn tại của media trong JSON response theo dot notation path.

    Ví dụ: dotpath="tweet.media" sẽ kiểm tra data["tweet"]["media"].
    Trả về True nếu giá trị tồn tại và không rỗng.
    """
    current = data
    for key in dotpath.split("."):
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return False
        if current is None:
            return False

    # Giá trị tồn tại: kiểm tra không rỗng
    if isinstance(current, (dict, list, str)):
        return bool(current)
    return current is not None


async def validate_via_api(
    session: aiohttp.ClientSession,
    original_url: str,
    proxy_domain: str,
) -> bool:
    """Xác thực proxy bằng JSON API (nếu có).

    Gửi GET request tới API endpoint, kiểm tra response JSON có chứa
    media objects theo đường dẫn đã cấu hình.
    Trả về True nếu có media, False nếu không hoặc lỗi.
    """
    api_url = _resolve_api_url(proxy_domain, original_url)
    if not api_url:
        return False

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
                return False

            data = await resp.json(content_type=None)
            if _check_media_in_json(data, media_path):
                return True

            print(
                f"[ProxyValidator] API không chứa media ({media_path}): {api_url}",
                flush=True,
            )
            return False

    except asyncio.TimeoutError:
        print(
            f"[ProxyValidator] API hết thời gian chờ: {api_url}",
            flush=True,
        )
        return False
    except (aiohttp.ClientError, ValueError) as e:
        print(
            f"[ProxyValidator] API lỗi kết nối: {api_url} - {e}",
            flush=True,
        )
        return False


# ---------------------------------------------------------------------------
# Bước 2: Xác thực qua OG metadata (fallback khi không có API)
# ---------------------------------------------------------------------------

async def validate_via_og_metadata(
    session: aiohttp.ClientSession,
    proxy_url: str,
) -> bool:
    """Xác thực proxy URL bằng cách kiểm tra OpenGraph/Twitter Card metadata.

    Gửi GET request với giới hạn đọc 16KB, phân tích HTML tìm meta tags.
    Trả về True nếu tìm thấy og:image, og:video, hoặc twitter:card/image/player.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0; +https://discord.app)",
            "Range": "bytes=0-16383",
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
                return False

            content = await resp.content.read(_MAX_READ_BYTES)
            html_text = content.decode("utf-8", errors="ignore")

            if _OG_META_PATTERN.search(html_text):
                return True

            print(
                f"[ProxyValidator] Không tìm thấy OG metadata: {proxy_url}",
                flush=True,
            )
            return False

    except asyncio.TimeoutError:
        print(
            f"[ProxyValidator] Hết thời gian chờ: {proxy_url}",
            flush=True,
        )
        return False
    except aiohttp.ClientError as e:
        print(
            f"[ProxyValidator] Lỗi kết nối: {proxy_url} - {e}",
            flush=True,
        )
        return False
    except Exception as e:
        print(
            f"[ProxyValidator] Lỗi không xác định: {proxy_url} - {e}",
            flush=True,
        )
        return False


# ---------------------------------------------------------------------------
# Chain of Responsibility: duyệt danh sách proxy theo thứ tự ưu tiên
# ---------------------------------------------------------------------------

async def find_valid_proxy(
    session: aiohttp.ClientSession,
    original_url: str,
    platform_key: str,
    guild_proxy_domains: list[str] | None = None,
) -> str | None:
    """Thực hiện Chain of Responsibility: thử từng proxy domain theo thứ tự ưu tiên.

    Nếu guild_proxy_domains được cung cấp (không phải None), sử dụng danh sách đó
    thay vì danh sách mặc định toàn cục. Điều này cho phép mỗi máy chủ tuỳ chỉnh
    thứ tự ưu tiên proxy riêng.

    Với mỗi proxy domain:
      1. Viết lại URL gốc sang proxy URL
      2. Nếu proxy có JSON API: xác thực qua API trước
      3. Nếu API thất bại hoặc không có API: xác thực qua OG metadata
      4. Proxy đầu tiên hợp lệ được trả về ngay lập tức

    Trả về proxy URL đầu tiên hợp lệ, hoặc None nếu tất cả đều thất bại.
    """
    if guild_proxy_domains is not None:
        proxy_domains = guild_proxy_domains
    else:
        proxy_domains = PROXY_DOMAINS.get(platform_key, [])

    if not proxy_domains:
        print(
            f"[ProxyValidator] Không có proxy nào được cấu hình cho nền tảng '{platform_key}'",
            flush=True,
        )
        return None

    for i, domain in enumerate(proxy_domains, start=1):
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

            # Bước 1: Thử xác thực qua JSON API (nếu có)
            if domain in PROXY_API_ENDPOINTS:
                is_valid = await validate_via_api(session, original_url, domain)
                if is_valid:
                    print(
                        f"[ProxyValidator] Xác thực API thành công: {domain} "
                        f"(nền tảng: {platform_key})",
                        flush=True,
                    )
                    return proxy_url

            # Bước 2: Fallback sang OG metadata
            is_valid = await validate_via_og_metadata(session, proxy_url)

        if is_valid:
            print(
                f"[ProxyValidator] Proxy hợp lệ (OG metadata): {domain} "
                f"(nền tảng: {platform_key})",
                flush=True,
            )
            return proxy_url

        print(
            f"[ProxyValidator] Proxy thất bại: {domain} (nền tảng: {platform_key})",
            flush=True,
        )

    print(
        f"[ProxyValidator] Tất cả proxy đã thất bại cho nền tảng '{platform_key}': "
        f"{original_url}",
        flush=True,
    )
    return None
