"""Bounded live Clef routing smoke; no Brave/Discord/Archive tool is executed.

Run manually in a credentialed environment:
    python scripts/smoke_clef_routing.py --live

Three Clef classifications only. It validates routing selection, not the
availability/permissions of downstream search providers or the end-to-end bot.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from features.assistant.providers.cloudflare import CloudflareDecisionRouter
from features.assistant.router import route_message


CASES = (
    ("public_web", "Giá xe máy điện mới nhất hôm nay là bao nhiêu?", "web.search"),
    ("guild_history", "Hồi đầu năm Theo từng nói gì về mua xe vậy?", "discord_history.search"),
    ("personal_archive", "Trong Archive có cái meme mèo nào không?", "archive.search"),
)
ALLOWED = frozenset({"web.search", "discord_history.search", "archive.search"})


async def smoke() -> int:
    clef = CloudflareDecisionRouter.from_env()
    if not clef.enabled:
        print("NOT VERIFIED: Clef lacks Cloudflare account/token or is code-disabled.")
        return 2

    failures = 0
    for name, query, expected in CASES:
        # No tool executor here: this only validates Clef + Python tool gates.
        decision = await route_message(
            query,
            cloudflare_router=clef,
            min_confidence=0.55,
            allowed_search_tools=ALLOWED,
        )
        # Source strings refer to Clef intent, not the typed tool name.
        expected_source = {
            "web.search": "clef_web_search",
            "discord_history.search": "clef_discord_history",
            "archive.search": "clef_archive_search",
        }[expected]
        passed = decision.tool == expected and decision.source == expected_source
        print(
            f"{name}: {'PASS' if passed else 'FAIL'} "
            f"source={decision.source} tool={decision.tool or 'none'} "
            f"clef_ms={decision.clef_ms:.0f}"
        )
        failures += not passed
    print(f"Clef live routing: {len(CASES) - failures}/{len(CASES)} passed; no search tools called.")
    return 1 if failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true",
        help="Explicitly authorize the three Workers AI classification requests.",
    )
    args = parser.parse_args()
    if not args.live:
        parser.error("Pass --live to explicitly allow up to three Clef inference requests.")
    raise SystemExit(asyncio.run(smoke()))
