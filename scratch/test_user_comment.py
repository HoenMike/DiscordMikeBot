import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def _extract_user_comment(content: str, urls: list[str]) -> str | None:
    """Trích xuất phần nội dung chữ/lời bình của người dùng, loại bỏ các link đã xử lý."""
    if not content:
        return None
    cleaned = content
    for u in urls:
        escaped_u = re.escape(u)
        pattern = re.compile(rf"(\|\|{escaped_u}\|\||<{escaped_u}>|{escaped_u})")
        cleaned = pattern.sub("", cleaned)
    cleaned = cleaned.strip()
    return cleaned if cleaned else None

def test_comment_extraction():
    cases = [
        ("haha nhìn buồn cười ghê https://x.com/user/status/12345", ["https://x.com/user/status/12345"], "haha nhìn buồn cười ghê"),
        ("https://x.com/user/status/12345 haha nhìn buồn cười ghê", ["https://x.com/user/status/12345"], "haha nhìn buồn cười ghê"),
        ("nhìn nè ||https://x.com/user/status/12345|| buồn cười ghê", ["https://x.com/user/status/12345"], "nhìn nè  buồn cười ghê"),
        ("<https://x.com/user/status/12345> xem đi", ["https://x.com/user/status/12345"], "xem đi"),
        ("https://x.com/user/status/12345", ["https://x.com/user/status/12345"], None),
        ("hai clip này hay https://x.com/a/status/1 https://x.com/b/status/2", ["https://x.com/a/status/1", "https://x.com/b/status/2"], "hai clip này hay"),
    ]

    for raw, urls, expected in cases:
        result = _extract_user_comment(raw, urls)
        print(f"Raw: {raw!r} => Extracted: {result!r} (Expected: {expected!r})")
        assert result == expected, f"Failed for {raw}: got {result!r} != {expected!r}"

    print("🎉 TẤT CẢ TEST TRÍCH XUẤT COMMENT ĐỀU ĐẠT CHUẨN!")

def _replace_url_in_content(content: str, original_url: str, new_url: str) -> str:
    """Thay thế chính xác URL gốc bằng proxy_url ngay tại vị trí ban đầu trong tin nhắn."""
    if not content:
        return new_url
    if original_url in content:
        return content.replace(original_url, new_url, 1)
    escaped = re.escape(original_url)
    return re.sub(escaped, new_url, content, count=1)

def test_in_place_replacement():
    raw = "test lại api liên kết thử? https://www.instagram.com/reel/DcVX1KrxAdS/ chữ dới này thì sao?"
    orig_url = "https://www.instagram.com/reel/DcVX1KrxAdS/"
    proxy_url = "https://vxinstagram.com/reel/DcVX1KrxAdS/"
    
    result = _replace_url_in_content(raw, orig_url, proxy_url)
    expected = "test lại api liên kết thử? https://vxinstagram.com/reel/DcVX1KrxAdS/ chữ dới này thì sao?"
    print(f"In-place Raw: {raw!r}\n=> Result: {result!r}")
    assert result == expected, f"Failed: {result!r} != {expected!r}"
    print("🎉 TEST IN-PLACE URL REPLACEMENT ĐẠT CHUẨN!")

if __name__ == "__main__":
    test_comment_extraction()
    test_in_place_replacement()
