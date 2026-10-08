from __future__ import annotations

import math
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Any, Dict


@dataclass(frozen=True)
class RouteDecision:
    intent: str
    tool: str | None = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    source: str = "local"
    route_ms: float = 0.0
    clef_ms: float = 0.0


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _extract_hours(text: str) -> float | None:
    folded = _fold(text).replace(",", ".")
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:h|gio|tieng)\b", folded)
    if not match:
        return None
    value = float(match.group(1))
    if value <= 0:
        return None
    return min(value, 168.0)


def _is_obvious_chat(text: str) -> bool:
    folded = _fold(text).strip()
    if not folded:
        return False

    return bool(
        re.match(
            r"^(?:hi|hello|hey|yo|alo|chao|xin\s+chao|test|ping)\b[\s,!?.:;-]*",
            folded,
        )
    )


def _safe_public_web_query(text: str) -> bool:
    """Avoid leaking Discord-private references through automatic web routing."""
    folded = _fold(text).strip().replace("đ", "d")
    if re.search(
        r"(?:<[@#][!&]?\d+>|discord(?:app)?\.com/channels/|@everyone|@here)",
        text, re.IGNORECASE,
    ):
        return False
    private_signals = (
        "tin nhan", "doan chat", "trong server", "tren discord",
        "hoi nay", "nay gio", "phia tren", "nguoi nay",
        "cai theo gui", "cai nay", "cai truoc", "archive",
        "da luu", "ban vua gui", "ban vua noi",
    )
    if any(signal in folded for signal in private_signals):
        return False
    # A private question with no external/public-information cues should not
    # send arbitrary chat text to Brave merely because Clef is uncertain.
    public_signals = (
        "moi nhat", "hom nay", "hien tai", "bay gio", "gia ",
        "tin tuc", "su kien", "cap nhat", "phien ban", "patch",
        "phat hanh", "chinh thuc", "ket qua", "thoi tiet",
        "latest", "news", "release", "today", "bao nhieu",
        "o dau", "gio mo cua", "thong bao moi",
    )
    return len(folded) >= 12 and any(s in folded for s in public_signals)


def _obvious_fresh_public_search(text: str) -> bool:
    """Conservative no-model rule for fresh public commodity prices.

    This deliberately does not attempt to extract entities from private chat.
    General external questions remain subject to Clef and source gating.
    """
    if not _safe_public_web_query(text):
        return False
    folded = _fold(text).replace("đ", "d")
    timely = any(cue in folded for cue in (
        "hom nay", "hien tai", "bay gio", "moi nhat", "cap nhat",
    ))
    topics = any(topic in folded for topic in (
        "gia xang", "gia dau", "gia vang", "ty gia",
    ))
    return timely and topics


def _current_weather_query(text: str) -> bool:
    """Daily/local weather is structured data, never raw AQI web snippets."""
    if not _safe_public_web_query(text):
        return False
    folded = _fold(text)
    if not any(x in folded for x in ("thoi tiet", "du bao thoi tiet", "nhiet do")):
        return False
    return any(x in folded for x in (
        "hom nay", "bay gio", "hien tai", "toi nay", "sang nay", "nhu nao",
        "the nao", "bao nhieu", "o bien hoa", "ngay mai",
    ))


def _safe_history_query(text: str) -> bool:
    """Only route bounded, explicitly history-related questions to guild search."""
    folded = _fold(text).replace("đ", "d")
    history_signals = (
        "tin nhan", "doan chat", "hoi dau nam", "dau nam",
        "hoi truoc", "thang ", "trong server", "tren discord",
        "da noi gi", "co nhan gi", "tung noi", "luc lai",
    )
    return any(s in folded for s in history_signals)


def _safe_archive_query(text: str) -> bool:
    folded = _fold(text).replace("đ", "d")
    return any(s in folded for s in (
        "archive", "toi da luu", "da luu", "da nho", "da save",
        "ban ghi nho", "kho luu tru",
    ))


def route_locally(text: str) -> RouteDecision:
    """Cheap deterministic pass before any model router is considered."""

    folded = _fold(text).strip()
    if not folded:
        return RouteDecision(intent="help", tool="help.show")

    # T22.5: a multi-source request is permitted only when the first stage
    # independently resolves to Discord History. Never extract a public search
    # term from a private result or ask Clef to compose an outbound query.
    from features.assistant.multisource import split_cross_source_request
    cross = split_cross_source_request(text)
    if cross and route_locally(cross.history_query).tool == "discord_history.search":
        return RouteDecision(
            intent="multi_source",
            tool="multi_source.search",
            arguments={
                "history_query": cross.history_query,
                "public_query": cross.public_query,
                "explicit_web": cross.explicit_web,
            },
            source="local_explicit_multisource",
        )

    # T22.1 is explicitly invoked only. T22.3 adds Clef source selection.
    # Keep the literal user wording for Brave (including Vietnamese accents).
    web_match = re.match(
        r"^(?:hay\s+)?(?:tim\s+(?:tiep\s+)?(?:tren\s+)?(?:web|mang|internet)|"
        r"tra\s+cuu\s+(?:tiep\s+)?(?:tren\s+)?(?:web|mang|internet)|"
        r"search\s+(?:web|online)|web\s+search)\b\s*[:,-]?\s*",
        folded,
    )
    if web_match:
        return RouteDecision(
            intent="web_search",
            tool="web.search",
            arguments={"query": text.strip()[web_match.end():].strip()},
        )

    # T22.2: explicit on-demand historical Discord search. Unlike Archive,
    # this can find messages that were never saved. Never send to Brave.
    history_folded = folded.replace("đ", "d")
    history_signals = (
        "tim tin nhan", "tim lai tin nhan", "tim doan chat",
        "tim lai doan chat", "luc lai", "search discord",
        "tim tren discord",
    )
    # "tìm xem" alone is ambiguous and should not hijack ordinary chat.
    explicit_history = any(s in history_folded for s in history_signals)
    contextual_recall = (
        "tim xem" in history_folded
        and (
            "<@" in text
            or any(s in history_folded for s in ("co nhan", "da noi", "noi gi", "tin nhan"))
        )
    )
    temporal_author_recall = (
        "<@" in text
        and any(s in history_folded for s in (
            "lan dau", "lan cuoi", "tin nhan dau tien",
            "tin nhan cu nhat", "tin nhan som nhat",
            "tin nhan gan nhat", "tin nhan moi nhat",
        ))
    )
    if explicit_history or contextual_recall or temporal_author_recall:
        return RouteDecision(
            intent="discord_history",
            tool="discord_history.search",
            arguments={"query": text.strip()},
        )

    # Distinguish "find earlier message" from finding a personally saved Archive
    # item, even if the user says "tìm lại".
    if (
        "tim lai" in history_folded
        and ("<@" in text or any(s in history_folded for s in (
            "hoi dau nam", "dau nam", "doan chat", "tin nhan",
            "thang ", "da noi", "tung noi",
        )))
        and not any(s in history_folded for s in ("archive", "da luu", "toi da luu"))
    ):
        return RouteDecision(
            intent="discord_history",
            tool="discord_history.search",
            arguments={"query": text.strip()},
        )

    forget_signals = (
        "quen #",
        "xoa #",
        "xoa muc",
        "xoa archive",
        "forget #",
        "delete archive",
    )
    if any(signal in folded for signal in forget_signals):
        match = re.search(r"(?:#|muc\s*#?|archive\s*#?)(\d+)\b", folded)
        if match:
            return RouteDecision(
                intent="archive_forget",
                tool="archive.forget",
                arguments={"archive_id": int(match.group(1))},
            )

    save_signals = (
        "nho cai nay",
        "luu cai nay",
        "save cai nay",
        "archive cai nay",
        "ghi nho cai nay",
        "cat cai nay",
        "cat lai cai nay",
        "nho link nay",
        "luu link nay",
        "nho anh nay",
        "luu anh nay",
    )
    if any(signal in folded for signal in save_signals):
        note = ""
        note_match = re.search(
            r"(?:note|ghi\s*ch[uú])\s*:\s*(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if note_match:
            note = note_match.group(1).strip()[:500]
        return RouteDecision(
            intent="archive_save",
            tool="archive.save",
            arguments={"note": note},
        )

    search_signals = (
        "tim lai",
        "kiem lai",
        "tim trong archive",
        "archive tim",
        "toi da luu",
        "da luu gi",
        "da nho gi",
        "archive cua toi",
    )
    if any(signal in folded for signal in search_signals):
        query = text.strip()
        cleanup = (
            r"^\s*(?:tim\s+lai|kiem\s+lai|tim\s+trong\s+archive|archive\s+tim|"
            r"toi\s+da\s+luu|da\s+luu\s+gi|da\s+nho\s+gi|archive\s+cua\s+toi)"
            r"\s*[:\-]?\s*"
        )
        query = re.sub(cleanup, "", _fold(query), flags=re.IGNORECASE).strip()
        return RouteDecision(
            intent="archive_search",
            tool="archive.search",
            arguments={
                "query": query,
                "semantic_query": text.strip(),
            },
        )

    help_signals = (
        "help",
        "huong dan",
        "lam duoc gi",
        "co the lam gi",
        "chuc nang gi",
    )
    if any(signal in folded for signal in help_signals):
        return RouteDecision(intent="help", tool="help.show")

    tarot_signal = any(signal in folded for signal in ("tarot", "boc bai", "boi bai"))
    if tarot_signal:
        if any(signal in folded for signal in ("daily", "hom nay", "ngay hom nay")):
            return RouteDecision(intent="tarot_daily", tool="tarot.daily")
        return RouteDecision(intent="tarot", tool="tarot.launch")

    summary_signals = (
        "tom tat",
        "catchup",
        "catch up",
        "nay gio",
        "tu chieu toi gio",
        "tu sang toi gio",
        "co gi dang chu y",
    )
    if any(signal in folded for signal in summary_signals):
        hours = _extract_hours(text)
        args: Dict[str, Any] = {}
        if hours is not None:
            args["hours"] = hours

        # Explicit author-scope ≠ ordinary channel recap. Keep stable mention
        # IDs and validate the actual Discord mentions before fetching.
        # "tóm tắt @X và @Y đã nói gì" is ambiguous: the tool asks for one.
        author_mention = re.findall(r"<@!?(\d{1,20})>", text)
        author_scope = any(signal in folded for signal in (
            "da nhan gi", "nhan gi", "da noi gi", "noi gi",
            "da chat gi", "da viet gi", "nhan nhung gi",
        )) or bool(re.search(r"tin nhan\s+cua\s+<@!?\d+>", folded))
        if author_mention and author_scope:
            args["author_ids"] = list(dict.fromkeys(int(x) for x in author_mention))
            return RouteDecision(
                intent="summary_member",
                tool="summary.member",
                arguments=args,
            )

        return RouteDecision(intent="summary", tool="summary.catchup", arguments=args)

    return RouteDecision(intent="chat")


async def route_message(
    text: str,
    cloudflare_router=None,
    min_confidence: float = 0.55,
    allowed_search_tools: frozenset[str] | None = None,
) -> RouteDecision:
    """Run deterministic routing first, then Clef only when classification is useful."""

    started = time.perf_counter()
    local = route_locally(text)

    if local.tool or not (text or "").strip():
        return replace(
            local,
            source="local_tool",
            route_ms=(time.perf_counter() - started) * 1000,
        )

    from core import constants as policy
    # Strictly public, explicitly current price checks should never pretend the
    # tool is unimplemented: the adapter provides a helpful missing-key status,
    # or runs with its durable Brave quota when credentials are present.
    if (
        policy.ASUMI_AUTO_SEARCH_ENABLED
        and policy.ASUMI_WEB_SEARCH_ENABLED
        and _obvious_fresh_public_search(text)
    ):
        return RouteDecision(
            intent="web_search",
            tool="web.search",
            arguments={"query": text.strip()},
            source="local_fresh_public",
            route_ms=(time.perf_counter() - started) * 1000,
        )

    # Never synthesize local weather from Brave AQI snippets: fetch actual
    # temperature, conditions and forecast from a dedicated weather API.
    if policy.ASUMI_WEATHER_ENABLED and _current_weather_query(text):
        return RouteDecision(
            intent="weather", tool="weather.forecast",
            arguments={"query": text.strip()},
            source="local_weather_facts",
            route_ms=(time.perf_counter() - started) * 1000,
        )

    # Greetings/test pings are clearly conversation. Calling Clef would only add
    # another network round-trip before the prose model.
    if _is_obvious_chat(text):
        return replace(
            local,
            source="local_chat",
            route_ms=(time.perf_counter() - started) * 1000,
        )

    if cloudflare_router is None or not getattr(cloudflare_router, "enabled", False):
        return replace(
            local,
            source="local_no_clef",
            route_ms=(time.perf_counter() - started) * 1000,
        )

    clef_started = time.perf_counter()
    try:
        clef = await cloudflare_router.classify(text)
    except Exception as exc:
        clef_ms = (time.perf_counter() - clef_started) * 1000
        print(
            f"⚠️ [Asumi Router] Clef unavailable after {clef_ms:.0f}ms: "
            f"{type(exc).__name__}: {str(exc)[:160]}",
            flush=True,
        )
        return replace(
            local,
            source="local_clef_error",
            route_ms=(time.perf_counter() - started) * 1000,
            clef_ms=clef_ms,
        )

    clef_ms = (time.perf_counter() - clef_started) * 1000
    # The provider normally validates confidence, but also enforce it here
    # because the router accepts injected adapters in tests and deployments.
    confidence = getattr(clef, "confidence", None)
    if (
        confidence is None
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
        or confidence < min_confidence
    ):
        return replace(
            local,
            source="local_low_confidence",
            route_ms=(time.perf_counter() - started) * 1000,
            clef_ms=clef_ms,
        )
    if getattr(clef, "intent", None) not in {
        "chat", "tarot", "summarize", "help",
        "web_search", "discord_history", "archive_search",
    }:
        return replace(
            local,
            source="local_clef_unknown",
            route_ms=(time.perf_counter() - started) * 1000,
            clef_ms=clef_ms,
        )

    if clef.intent == "tarot":
        routed = RouteDecision(intent="tarot", tool="tarot.launch")
    elif clef.intent == "summarize":
        args: Dict[str, Any] = {}
        hours = _extract_hours(text)
        if hours is not None:
            args["hours"] = hours
        routed = RouteDecision(intent="summary", tool="summary.catchup", arguments=args)
    elif clef.intent == "help":
        routed = RouteDecision(intent="help", tool="help.show")
    elif (
        clef.intent == "web_search"
        and "web.search" in (allowed_search_tools or ())
        and _safe_public_web_query(text)
    ):
        routed = RouteDecision(
            intent="web_search", tool="web.search",
            arguments={"query": text.strip()},
        )
    elif (
        clef.intent == "discord_history"
        and "discord_history.search" in (allowed_search_tools or ())
        and _safe_history_query(text)
    ):
        routed = RouteDecision(
            intent="discord_history", tool="discord_history.search",
            arguments={"query": text.strip()},
        )
    elif (
        clef.intent == "archive_search"
        and "archive.search" in (allowed_search_tools or ())
        and _safe_archive_query(text)
    ):
        routed = RouteDecision(
            intent="archive_search", tool="archive.search",
            arguments={"query": _fold(text.strip()), "semantic_query": text.strip()},
        )
    else:
        routed = local

    return replace(
        routed,
        source=(
            f"clef_{clef.intent}"
            if routed is not local
            else (
                f"clef_{clef.intent}_blocked"
                if clef.intent in {"web_search", "discord_history", "archive_search"}
                else f"clef_{clef.intent}"
            )
        ),
        route_ms=(time.perf_counter() - started) * 1000,
        clef_ms=clef_ms,
    )
