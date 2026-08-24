import aiohttp
from dataclasses import dataclass, field
from urllib.parse import quote


@dataclass
class PostData:
    platform: str
    author: str = "Unknown"
    author_url: str | None = None
    author_avatar: str | None = None
    text: str | None = None
    media_urls: list[str] = field(default_factory=list)
    media_type: str = "text"
    is_nsfw: bool = False
    is_spoiler: bool = False
    likes: int | None = None
    comments: int | None = None
    retweets: int | None = None
    url: str = ""
    timestamp: str | None = None


async def fetch_twitter(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        username, tweet_id = match.group(1), match.group(2)
        api_url = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        tweet = data.get("tweet", {})
        if not tweet:
            return None

        media_urls = []
        media_type = "text"
        media_obj = tweet.get("media", {})
        if media_obj:
            photos = media_obj.get("photos", [])
            for photo in photos:
                if photo.get("url"):
                    media_urls.append(photo["url"])

            videos = media_obj.get("videos", [])
            if videos:
                for video in videos:
                    if video.get("thumbnail_url"):
                        media_urls.append(video["thumbnail_url"])
                media_type = "video"
            elif len(media_urls) > 1:
                media_type = "gallery"
            elif len(media_urls) == 1:
                media_type = "image"

        author = tweet.get("author", {})
        return PostData(
            platform="twitter",
            author=author.get("name", "Unknown"),
            author_url=f"https://x.com/{author.get('screen_name', '')}",
            author_avatar=author.get("avatar_url"),
            text=tweet.get("text"),
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=tweet.get("possibly_sensitive", False),
            likes=tweet.get("likes"),
            comments=tweet.get("replies"),
            retweets=tweet.get("retweets"),
            url=tweet.get("url", url),
            timestamp=tweet.get("created_at"),
        )
    except Exception as e:
        print(f"[Fetcher/Twitter] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_reddit(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        clean_path = match.group(1).rstrip("/")
        api_url = f"https://www.reddit.com{clean_path}.json"

        headers = {"User-Agent": "MikeDaBot/1.0"}
        async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        if not data or not isinstance(data, list):
            return None

        post = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
        if not post:
            return None

        media_urls = []
        media_type = "text"

        post_url = post.get("url", "")
        if any(post_url.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]):
            media_urls.append(post_url)
            media_type = "image"

        if post.get("is_gallery") and post.get("media_metadata"):
            for item_id, item_data in post["media_metadata"].items():
                if item_data.get("s", {}).get("u"):
                    img_url = item_data["s"]["u"].replace("&amp;", "&")
                    media_urls.append(img_url)
            if len(media_urls) > 1:
                media_type = "gallery"
            elif len(media_urls) == 1:
                media_type = "image"

        if post.get("is_video") and post.get("thumbnail") and post["thumbnail"].startswith("http"):
            media_urls.append(post["thumbnail"])
            media_type = "video"

        if not media_urls and post.get("preview", {}).get("images"):
            preview_url = post["preview"]["images"][0].get("source", {}).get("url", "")
            if preview_url:
                media_urls.append(preview_url.replace("&amp;", "&"))
                media_type = "image"

        title = post.get("title", "")
        selftext = post.get("selftext", "")[:500]
        text_content = f"**{title}**\n\n{selftext}".strip() if selftext else f"**{title}**"

        return PostData(
            platform="reddit",
            author=f"u/{post.get('author', 'deleted')}",
            author_url=f"https://www.reddit.com/user/{post.get('author', '')}",
            text=text_content,
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=post.get("over_18", False),
            is_spoiler=post.get("spoiler", False),
            likes=post.get("ups"),
            comments=post.get("num_comments"),
            url=f"https://www.reddit.com{post.get('permalink', '')}",
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/Reddit] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_tiktok(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        api_url = f"https://api.vxtiktok.com/api/v1/fetch?url={quote(url, safe='')}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        video_data = data.get("data", {})
        if not video_data:
            return None

        author_info = video_data.get("author", {})
        stats = video_data.get("statistics", {})

        media_urls = []
        cover = video_data.get("cover")
        dynamic_cover = video_data.get("dynamicCover")
        if dynamic_cover:
            media_urls.append(dynamic_cover)
        elif cover:
            media_urls.append(cover)

        return PostData(
            platform="tiktok",
            author=author_info.get("nickname", author_info.get("uniqueId", "Unknown")),
            author_url=f"https://www.tiktok.com/@{author_info.get('uniqueId', '')}",
            author_avatar=author_info.get("avatarThumb"),
            text=video_data.get("title") or video_data.get("desc"),
            media_urls=media_urls,
            media_type="video",
            is_nsfw=False,
            likes=stats.get("diggCount") or stats.get("likeCount"),
            comments=stats.get("commentCount"),
            retweets=stats.get("shareCount"),
            url=url,
            timestamp=video_data.get("createTime"),
        )
    except Exception as e:
        print(f"[Fetcher/TikTok] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_instagram(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        shortcode = match.group(1)
        original_url = f"https://www.instagram.com/p/{shortcode}/"
        api_url = f"https://api.ddinstagram.com/oembed?url={quote(original_url, safe='')}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        media_urls = []
        if data.get("thumbnail_url"):
            media_urls.append(data["thumbnail_url"])

        media_type = "video" if data.get("type") == "video" else "image"

        return PostData(
            platform="instagram",
            author=data.get("author_name", "Unknown"),
            author_url=data.get("author_url"),
            text=data.get("title"),
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=False,
            url=original_url,
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/Instagram] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_facebook(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        api_url = f"https://www.facebook.com/plugins/post/oembed.json/?url={quote(url, safe='')}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        return PostData(
            platform="facebook",
            author=data.get("author_name", "Unknown"),
            author_url=data.get("author_url"),
            text=data.get("title") or "Facebook Post",
            media_urls=[],
            media_type="text",
            is_nsfw=False,
            url=url,
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/Facebook] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_bluesky(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        handle, post_id = match.group(1), match.group(2)

        if not handle.startswith("did:"):
            resolve_url = f"https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle?handle={handle}"
            async with session.get(resolve_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return None
                resolve_data = await resp.json()
                did = resolve_data.get("did")
        else:
            did = handle

        if not did:
            return None

        at_uri = f"at://{did}/app.bsky.feed.post/{post_id}"
        api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri={quote(at_uri, safe='')}&depth=0"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        thread = data.get("thread", {})
        post = thread.get("post", {})
        record = post.get("record", {})
        author_info = post.get("author", {})

        media_urls = []
        media_type = "text"
        embed_data = post.get("embed", {})

        if embed_data:
            images = embed_data.get("images", [])
            if images:
                for img in images:
                    thumb = img.get("thumb") or img.get("fullsize")
                    if thumb:
                        media_urls.append(thumb)
                media_type = "gallery" if len(media_urls) > 1 else "image"

            external = embed_data.get("external", {})
            if external and external.get("thumb"):
                media_urls.append(external["thumb"])
                media_type = "image"

        is_nsfw = any(label.get("val") in ("nsfw", "porn", "sexual", "nudity") for label in post.get("labels", []))

        return PostData(
            platform="bluesky",
            author=author_info.get("displayName", author_info.get("handle", "Unknown")),
            author_url=f"https://bsky.app/profile/{author_info.get('handle', '')}",
            author_avatar=author_info.get("avatar"),
            text=record.get("text"),
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=is_nsfw,
            likes=post.get("likeCount"),
            comments=post.get("replyCount"),
            retweets=post.get("repostCount"),
            url=url,
            timestamp=record.get("createdAt"),
        )
    except Exception as e:
        print(f"[Fetcher/Bluesky] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_twitch(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        api_url = f"https://api.twitch.tv/v5/oembed?url={quote(url, safe='')}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        media_urls = []
        if data.get("thumbnail_url"):
            media_urls.append(data["thumbnail_url"])

        return PostData(
            platform="twitch",
            author=data.get("author_name", "Unknown"),
            author_url=f"https://www.twitch.tv/{data.get('author_name', '')}",
            text=data.get("title", "Twitch Clip"),
            media_urls=media_urls,
            media_type="video",
            is_nsfw=False,
            url=url,
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/Twitch] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_pixiv(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        artwork_id = match.group(1)
        api_url = f"https://phixiv.net/api/info?id={artwork_id}"

        async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        media_urls = []
        media_type = "image"

        image_proxy_url = data.get("image_proxy_url")
        if image_proxy_url:
            media_urls.append(image_proxy_url)

        urls_list = data.get("urls", [])
        if urls_list and len(urls_list) > 1:
            media_urls = urls_list[:4]
            media_type = "gallery"
        elif urls_list and len(urls_list) == 1:
            media_urls = urls_list

        tags = data.get("tags", [])
        is_nsfw = False
        if isinstance(tags, list):
            for tag in tags:
                tag_name = tag if isinstance(tag, str) else tag.get("name", "")
                if tag_name.upper() in ("R-18", "R-18G"):
                    is_nsfw = True
                    break

        artist = data.get("artist_name") or data.get("user_name", "Unknown")
        artist_id = data.get("artist_id") or data.get("user_id")

        return PostData(
            platform="pixiv",
            author=artist,
            author_url=f"https://www.pixiv.net/users/{artist_id}" if artist_id else None,
            author_avatar=data.get("artist_avatar") or data.get("profile_img"),
            text=data.get("title") or data.get("description"),
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=is_nsfw,
            likes=data.get("like_count") or data.get("total_bookmarks"),
            comments=data.get("comment_count"),
            url=f"https://www.pixiv.net/artworks/{artwork_id}",
            timestamp=data.get("upload_timestamp") or data.get("create_date"),
        )
    except Exception as e:
        print(f"[Fetcher/Pixiv] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_threads(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        username = match.group(1) if len(match.groups()) >= 1 else "threads_user"
        post_id = match.group(2) if len(match.groups()) >= 2 else ""
        original_url = f"https://www.threads.net/@{username}/post/{post_id}" if post_id else url

        oembed_url = f"https://www.threads.net/oembed/?url={quote(original_url, safe='')}"

        async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        media_urls = []
        if data.get("thumbnail_url"):
            media_urls.append(data["thumbnail_url"])

        media_type = "video" if data.get("type") == "video" else "image" if media_urls else "text"

        return PostData(
            platform="threads",
            author=data.get("author_name", f"@{username}"),
            author_url=f"https://www.threads.net/@{username}",
            text=data.get("title"),
            media_urls=media_urls,
            media_type=media_type,
            is_nsfw=False,
            url=original_url,
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/Threads] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


async def fetch_youtube(session: aiohttp.ClientSession, url: str, match) -> PostData | None:
    try:
        video_id = match.group(1)
        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        oembed_url = f"https://www.youtube.com/oembed?url={quote(canonical_url, safe='')}&format=json"

        async with session.get(oembed_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        media_urls = []
        if data.get("thumbnail_url"):
            media_urls.append(data["thumbnail_url"])
        else:
            # Fallback: sử dụng thumbnail mặc định của YouTube
            media_urls.append(f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg")

        return PostData(
            platform="youtube",
            author=data.get("author_name", "Unknown"),
            author_url=data.get("author_url"),
            text=data.get("title", "YouTube Video"),
            media_urls=media_urls,
            media_type="video",
            is_nsfw=False,
            url=canonical_url,
            timestamp=None,
        )
    except Exception as e:
        print(f"[Fetcher/YouTube] Lỗi khi tải dữ liệu {url}: {e}", flush=True)
        return None


FETCHER_MAP = {
    "twitter": fetch_twitter,
    "reddit": fetch_reddit,
    "tiktok": fetch_tiktok,
    "instagram": fetch_instagram,
    "facebook": fetch_facebook,
    "bluesky": fetch_bluesky,
    "twitch": fetch_twitch,
    "pixiv": fetch_pixiv,
    "threads": fetch_threads,
    "youtube": fetch_youtube,
}

