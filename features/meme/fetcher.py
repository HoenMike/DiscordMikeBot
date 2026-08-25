import aiohttp
import urllib.parse
import re
import random
from typing import List, Dict, Optional, Any
import config


class MemeFetcher:
    """Thu thập hình ảnh & GIF Meme từ nhiều nguồn: Web Scraper, Google CSE, Tenor, Giphy và Imgflip."""

    @staticmethod
    async def fetch_web_images(query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Quét và trích xuất hình ảnh/GIF độ phân giải cao từ Web Search (Bing Engine).
        Hỗ trợ tìm kiếm chuẩn xác cả tiếng Việt lẫn tiếng Anh mà không cần API key.
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
        }
        encoded = urllib.parse.quote(f"{query} meme")
        url = f"https://www.bing.com/images/search?q={encoded}&setlang=vi&form=HDRSC2&first=1"

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
                            if any(ext in clean_u.lower() for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
                                is_gif = ".gif" in clean_u.lower()
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
            "q": f"{query} meme",
            "searchType": "image",
            "num": min(limit, 10),
            "safe": "active"
        }

        results = []
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for item in data.get("items", []):
                            link = item.get("link")
                            if link:
                                is_gif = item.get("fileFormat", "").lower() == "image/gif" or ".gif" in link.lower()
                                results.append({
                                    "url": link,
                                    "media_type": "gif" if is_gif else "image",
                                    "source": "google_cse",
                                    "title": item.get("title", "")
                                })
        except Exception as e:
            print(f"[MemeFetcher] Lỗi Google CSE API: {e}", flush=True)

        return results

    @staticmethod
    async def fetch_tenor_gifs(query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Tìm kiếm GIF động từ Tenor API v2 (nếu đã cấu hình TENOR_API_KEY)."""
        if not config.TENOR_API_KEY:
            return []

        url = "https://tenor.googleapis.com/v2/search"
        params = {
            "key": config.TENOR_API_KEY,
            "q": query,
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
                            media = item.get("media_formats", {}).get("gif", {})
                            gif_url = media.get("url")
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
        """Tìm kiếm GIF động từ Giphy API (nếu đã cấu hình GIPHY_API_KEY)."""
        if not config.GIPHY_API_KEY:
            return []

        url = "https://api.giphy.com/v1/gifs/search"
        params = {
            "api_key": config.GIPHY_API_KEY,
            "q": query,
            "limit": limit,
            "rating": "g"
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
        Hợp nhất tìm kiếm meme từ tất cả các nguồn theo thứ tự ưu tiên:
        1. Google CSE (nếu có key)
        2. Tenor / Giphy (nếu có key)
        3. Web Image Scraper theo raw_prompt (ví dụ: 'kek meme')
        4. Web Image Scraper theo en_keywords (quốc tế)
        5. Web Image Scraper theo vi_keywords (tiếng Việt)
        """
        all_candidates = []

        # 1. Thử Google CSE
        google_res = await cls.fetch_google_cse(vi_keywords)
        if google_res:
            all_candidates.extend(google_res)

        # 2. Thử Tenor / Giphy
        tenor_res = await cls.fetch_tenor_gifs(en_keywords)
        if tenor_res:
            all_candidates.extend(tenor_res)

        giphy_res = await cls.fetch_giphy_gifs(en_keywords)
        if giphy_res:
            all_candidates.extend(giphy_res)

        # 3. Quét Web theo từ khóa gốc của user (cực kỳ chuẩn xác cho tên meme cụ thể như 'kek', 'pepe'...)
        if raw_prompt:
            clean_raw = raw_prompt.strip()
            query_raw = f"{clean_raw} meme" if "meme" not in clean_raw.lower() else clean_raw
            web_raw_res = await cls.fetch_web_images(query_raw, limit=8)
            if web_raw_res:
                all_candidates.extend(web_raw_res)

        # 4. Quét Web theo từ khóa tiếng Anh (bổ sung ảnh/GIF quốc tế)
        if en_keywords:
            web_en_res = await cls.fetch_web_images(en_keywords, limit=8)
            if web_en_res:
                all_candidates.extend(web_en_res)

        # 5. Quét Web theo từ khóa tiếng Việt
        if vi_keywords:
            web_vi_res = await cls.fetch_web_images(vi_keywords, limit=8)
            if web_vi_res:
                all_candidates.extend(web_vi_res)

        # Khử trùng lặp URL
        unique_results = []
        seen_urls = set()
        for c in all_candidates:
            if c["url"] not in seen_urls:
                seen_urls.add(c["url"])
                unique_results.append(c)

        return unique_results
