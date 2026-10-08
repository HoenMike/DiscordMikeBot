"""Private R2 image evidence, validated and uploaded before ticket commit.

No public bucket URL. Original Discord CDN references are not durable.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import uuid
from dataclasses import dataclass
from typing import Any

from PIL import Image, UnidentifiedImageError

from core import constants as settings


class EvidenceError(Exception):
    pass


@dataclass(frozen=True)
class UploadedEvidence:
    key: str
    media_type: str
    bytes_count: int
    sha256: str
    source_message_id: int


def _clean_image(data: bytes) -> tuple[bytes, str]:
    if len(data) > settings.ASUMI_FEEDBACK_IMAGE_MAX_BYTES:
        raise EvidenceError("Ảnh vượt giới hạn dung lượng.")
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in {"PNG", "JPEG", "WEBP"}:
                raise EvidenceError("Chỉ nhận PNG, JPG hoặc WebP.")
            if im.width < 1 or im.height < 1 or im.width * im.height > settings.ASUMI_FEEDBACK_IMAGE_MAX_PIXELS:
                raise EvidenceError("Kích thước ảnh không hợp lệ.")
            # Re-encode to avoid preserving image EXIF/GPS or untrusted metadata.
            im.load()
            cleaned = im.convert("RGB")
            target = io.BytesIO()
            cleaned.save(target, "PNG", optimize=True)
            payload = target.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise EvidenceError("Không đọc được ảnh đính kèm hợp lệ.") from exc
    if len(payload) > settings.ASUMI_FEEDBACK_IMAGE_MAX_BYTES:
        raise EvidenceError("Ảnh sau khi xử lý vượt giới hạn; hãy giảm kích thước.")
    return payload, "image/png"


class PrivateEvidenceStore:
    def __init__(self, *, client: Any = None):
        self._client = client
        self.bucket = os.getenv("ASUMI_FEEDBACK_R2_BUCKET", "").strip()

    @property
    def configured(self) -> bool:
        return bool(
            self.bucket and os.getenv("CLOUDFLARE_ACCOUNT_ID", "").strip()
            and os.getenv("ASUMI_FEEDBACK_R2_ACCESS_KEY_ID", "").strip()
            and os.getenv("ASUMI_FEEDBACK_R2_SECRET_ACCESS_KEY", "").strip()
        )

    def _s3(self):
        if self._client is not None:
            return self._client
        if not self.configured:
            raise EvidenceError("Kho ảnh riêng tư chưa được cấu hình. Ticket kèm ảnh chưa thể lưu.")
        import boto3
        from botocore.config import Config
        account = os.environ["CLOUDFLARE_ACCOUNT_ID"].strip()
        return boto3.client(
            "s3",
            endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["ASUMI_FEEDBACK_R2_ACCESS_KEY_ID"].strip(),
            aws_secret_access_key=os.environ["ASUMI_FEEDBACK_R2_SECRET_ACCESS_KEY"].strip(),
            region_name="auto",
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10, retries={"max_attempts": 1}),
        )

    async def put_attachment(self, attachment: Any, *, guild_id: int, source_message_id: int) -> UploadedEvidence:
        if not self.configured and self._client is None:
            raise EvidenceError("Chưa cấu hình kho ảnh riêng tư R2.")
        size = getattr(attachment, "size", 0)
        if size <= 0 or size > settings.ASUMI_FEEDBACK_IMAGE_MAX_BYTES:
            raise EvidenceError("Ảnh quá lớn hoặc rỗng (tối đa 8 MiB).")
        claimed_type = (getattr(attachment, "content_type", "") or "").lower().split(";")[0]
        if claimed_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise EvidenceError("Chỉ nhận ảnh PNG, JPG và WebP.")
        try:
            payload = await attachment.read()
        except Exception as exc:
            raise EvidenceError("Không tải được ảnh từ Discord. Hãy gửi lại.") from exc
        clean, mime = await asyncio.to_thread(_clean_image, payload)
        digest = hashlib.sha256(clean).hexdigest()
        key = f"feedback/{int(guild_id)}/{uuid.uuid4().hex}.png"
        try:
            await asyncio.to_thread(
                self._s3().put_object, Bucket=self.bucket, Key=key,
                Body=clean, ContentType=mime,
                Metadata={"sha256": digest, "source": "discord-feedback"},
            )
        except Exception as exc:
            raise EvidenceError("Lưu ảnh vào R2 thất bại; ticket chưa được gửi.") from exc
        return UploadedEvidence(
            key=key, media_type=mime, bytes_count=len(clean),
            sha256=digest, source_message_id=int(source_message_id),
        )

    async def delete(self, key: str) -> None:
        if not key.startswith("feedback/") or not self.bucket:
            return
        try:
            await asyncio.to_thread(self._s3().delete_object, Bucket=self.bucket, Key=key)
        except Exception:
            # Orphans must be recorded and reconciled by the retention job.
            print("[Feedback] R2 cleanup failed (orphan evidence); review storage audit.", flush=True)


evidence_store = PrivateEvidenceStore()
