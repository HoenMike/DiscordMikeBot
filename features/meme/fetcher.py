import aiohttp
import urllib.parse
import re
import random
from typing import List, Dict, Optional, Any
import config


MEME_TRUSTED_DOMAINS = [
    "tenor.com",
    "giphy.com",
    "imgflip.com",
    "knowyourmeme.com",
    "kym-cdn.com",
    "redd.it",
    "reddit.com",
    "hoyolab.com",
    "zerochan.net",
    "gamebanana.com",
    "fptshop.com.vn",
    "sforum.vn",
    "bom.edu.vn",
    "khoanhdep.com",
    "genk.mediacdn.vn",
    "media.makeameme.org",
    "danbooru",
    "safebooru",
]

BAD_KEYWORDS = [
    "shopee",
    "lazada",
    "tiki",
    "amazon",
    "aliexpress",
    "product",
    "catalog",
    "san-pham",
    "mua-ban",
    "cadbury",
    "almonds",
    "chocolate",
    "pricing",
    "store",
    "shop",
]


def score_meme_candidate(url: str, query: str = "") -> int:
    """Chấm điểm ứng cử viên meme: Ưu tiên nguồn uy tín và ảnh động GIF, trừ điểm trang bán hàng."""
    score = 0
    u_lower = url.lower()

    # 1. Điểm cộng cho các website chuyên về Meme / GIF / Gaming / Anime
    for d in MEME_TRUSTED_DOMAINS:
        if d in u_lower:
            score += 50
            break

    # 2. Điểm cộng rất lớn cho ảnh GIF động (chuẩn reaction meme)
    if ".gif" in u_lower or "tenor.com" in u_lower or "giphy.com" in u_lower:
        score += 30

    # 3. Trừ điểm nặng các trang bán hàng, thương mại điện tử, danh mục sản phẩm
    for bad in BAD_KEYWORDS:
        if bad in u_lower:
            score -= 100

    return score


class MemeFetcher:
    """Thu thập hình ảnh & GIF Meme từ nhiều nguồn: Web Scraper, Google CSE, Tenor, Giphy và Imgflip."""

    @staticmethod
    async def fetch_web_images(query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Quét và trích xuất hình ảnh/GIF độ phân giải cao từ Web Search (Bing Engine).
        Hỗ trợ tìm kiếm chuẩn xác cả tiếng Việt lẫn tiếng Anh mà không cần API key.
        """
        if not query or not query.strip():
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9,vi-VN,vi;q=0.8",
        }
        clean_q = query.strip()
        encoded = urllib.parse.quote(clean_q)
        url = f"https://www.bing.com/images/search?q={encoded}&form=HDRSC2&first=1"

        results = []
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        murls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', text)
                        if not murls:
                            murls = re.findall(r'"murl":"(https?://[^"]+)"', text)

                        for u in murls:
                            clean_u = u.strip()
                            is_valid_media = any(ext in clean_u.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]) or "tenor.com" in clean_u.lower() or "giphy.com" in clean_u.lower()
                            if is_valid_media:
                                is_gif = ".gif" in clean_u.lower() or "tenor.com" in clean_u.lower() or "giphy.com" in clean_u.lower()
                                results.append({
                                    "url": clean_u,
                                    "media_type": "gif" if is_gif else "image",
                                    "source": "web_search"
                                })
                                if len(results) >= limit:
                                    break
        except Exception as e:
            print(f"[MemeFetcher] Lỗi quét ảnh Web: {e}", flush=True)

        return results

    @staticmethod
    async def fetch_google_cse(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm ảnh chính thức qua Google Custom Search Engine (nếu đã cấu hình API Key)."""
        if not config.GOOGLE_CSE_API_KEY or not config.GOOGLE_CSE_CX:
            return []

        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": config.GOOGLE_CSE_API_KEY,
            "cx": config.GOOGLE_CSE_CX,
            "q": query,
            "searchType": "image",
            "num": limit,
            "safe": "off"
        }

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("items", []):
                            img_url = item.get("link")
                            if img_url:
                                is_gif = item.get("fileFormat", "").lower() == "image/gif" or ".gif" in img_url.lower()
                                results.append({
                                    "url": img_url,
                                    "media_type": "gif" if is_gif else "image",
                                    "source": "google_cse",
                                    "title": item.get("title", "")
                                })
        except Exception as e:
            print(f"[MemeFetcher] Lỗi Google CSE API: {e}", flush=True)

        return results

    @staticmethod
    async def fetch_tenor_gifs(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm ảnh động chính thức qua Tenor API (nếu có key)."""
        if not config.TENOR_API_KEY:
            return []

        url = "https://tenor.googleapis.com/v2/search"
        params = {
            "q": query,
            "key": config.TENOR_API_KEY,
            "limit": limit,
            "media_filter": "gif",
            "contentfilter": "medium"
        }

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("results", []):
                            gif_url = item.get("media_formats", {}).get("gif", {}).get("url")
                            if gif_url:
                                results.append({
                                    "url": gif_url,
                                    "media_type": "gif",
                                    "source": "tenor",
                                    "title": item.get("content_description", "")
                                })
        except Exception as e:
            print(f"[MemeFetcher] Lỗi Tenor API: {e}", flush=True)

        return results

    @staticmethod
    async def fetch_giphy_gifs(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm ảnh động chính thức qua Giphy API (nếu có key)."""
        if not config.GIPHY_API_KEY:
            return []

        url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": config.GIPHY_API_KEY,
            "q": query,
            "limit": limit,
            "rating": "pg-13"
        }

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("data", []):
                            gif_url = item.get("images", {}).get("original", {}).get("url")
                            if gif_url:
                                results.append({
                                    "url": gif_url,
                                    "media_type": "gif",
                                    "source": "giphy",
                                    "title": item.get("title", "")
                                })
        except Exception as e:
            print(f"[MemeFetcher] Lỗi Giphy API: {e}", flush=True)

        return results

    @classmethod
    async def discover_meme(
        cls,
        vi_keywords: str,
        en_keywords: str,
        raw_prompt: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Hợp nhất tìm kiếm meme từ tất cả các nguồn theo chuỗi biến thể tối ưu kèm thuật toán xếp hạng:
        1. Google CSE / Tenor / Giphy (nếu có key)
        2. Quét các biến thể từ khóa trên Web: f"{raw_prompt} gif", f"{raw_prompt} meme", spaced words
        3. Thuật toán Smart Scoring: Ưu tiên Tenor/Giphy/Reddit/Meme Hubs và loại bỏ ảnh rác/bán hàng
        """
        all_candidates = []
        seen_urls = set()

        def add_items(items: List[Dict[str, Any]]):
            for it in items:
                if it["url"] not in seen_urls:
                    seen_urls.add(it["url"])
                    all_candidates.append(it)

        # 1. Thử các API có Key
        if config.GOOGLE_CSE_API_KEY:
            add_items(await cls.fetch_google_cse(raw_prompt or vi_keywords))
        if config.TENOR_API_KEY:
            add_items(await cls.fetch_tenor_gifs(raw_prompt or en_keywords))
        if config.GIPHY_API_KEY:
            add_items(await cls.fetch_giphy_gifs(raw_prompt or en_keywords))

        # 2. Quét Web theo các biến thể thông minh
        if raw_prompt:
            clean_raw = raw_prompt.strip()
            # Ưu tiên tìm GIF động trước (chuẩn reaction meme)
            add_items(await cls.fetch_web_images(f"{clean_raw} gif", limit=8))
            add_items(await cls.fetch_web_images(f"{clean_raw} meme", limit=8))

            # Biến thể tách từ (VD: 'nono' -> 'no no')
            if "nono" in clean_raw.lower():
                spaced = re.sub(r'nono', 'no no', clean_raw, flags=re.IGNORECASE)
                add_items(await cls.fetch_web_images(f"{spaced} gif", limit=6))
                add_items(await cls.fetch_web_images(spaced, limit=6))

            add_items(await cls.fetch_web_images(clean_raw, limit=6))

        # 3. Quét Web theo từ khóa tiếng Anh & tiếng Việt AI đề xuất
        if en_keywords and en_keywords != raw_prompt:
            add_items(await cls.fetch_web_images(en_keywords, limit=6))
        if vi_keywords and vi_keywords != raw_prompt:
            add_items(await cls.fetch_web_images(vi_keywords, limit=6))

        # 4. Sắp xếp thứ hạng (Smart Ranking)
        sorted_candidates = sorted(
            all_candidates,
            key=lambda x: score_meme_candidate(x["url"], raw_prompt or ""),
            reverse=True
        )

        return sorted_candidates
