from dataclasses import dataclass


@dataclass
class PreviewSafety:
    is_nsfw: bool = False


@dataclass(frozen=True)
class PreviewResult:
    status: str = "failed"
    tier: str = "none"
    reason: str = "no_usable_preview"
    platform: str = ""
    proxy_domain: str | None = None
    origin_message_id: int | None = None
    preview_message_id: int | None = None
    unfurl_verified: bool = False
    used_fallback: bool = False
    fallback_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.status == "success"

    def __bool__(self) -> bool:
        return self.success
