from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import aiohttp


class SemanticUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class SemanticMatch:
    archive_id: int
    score: float


class ArchiveSemanticIndex:
    """Optional Cloudflare Workers AI + Vectorize semantic index.

    Canonical Archive records always remain in Turso/SQLite. Vectorize is a
    derived index only and may fail without affecting Save/Search/Forget.
    """

    def __init__(
        self,
        *,
        account_id: str = "",
        ai_token: str = "",
        vectorize_token: str = "",
        enabled: bool = False,
        index_name: str = "asumi-archive-v1",
        embedding_model: str = "@cf/baai/bge-m3",
        dimensions: int = 1024,
        timeout_seconds: float = 6.0,
        min_score: float = 0.45,
    ):
        self.account_id = account_id.strip()
        self.ai_token = ai_token.strip()
        self.vectorize_token = (vectorize_token or ai_token).strip()
        self.configured = bool(
            enabled and self.account_id and self.ai_token and self.vectorize_token
        )
        self.index_name = index_name.strip() or "asumi-archive-v1"
        self.embedding_model = embedding_model.strip() or "@cf/baai/bge-m3"
        self.dimensions = int(dimensions)
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.min_score = max(0.0, min(float(min_score), 1.0))
        self._index_ready = False
        self._blocked_reason = ""

    @classmethod
    def from_env(cls) -> "ArchiveSemanticIndex":
        enabled = os.getenv("CF_ARCHIVE_SEMANTIC_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "on"
        }
        ai_token = (
            os.getenv("CLOUDFLARE_API_TOKEN", "").strip()
            or os.getenv("CLOUDFLARE_AUTH_TOKEN", "").strip()
        )
        return cls(
            account_id=os.getenv("CLOUDFLARE_ACCOUNT_ID", ""),
            ai_token=ai_token,
            vectorize_token=os.getenv("CLOUDFLARE_VECTORIZE_TOKEN", ""),
            enabled=enabled,
            index_name=os.getenv("CF_ARCHIVE_VECTORIZE_INDEX", "asumi-archive-v1"),
            embedding_model=os.getenv(
                "CF_ARCHIVE_EMBEDDING_MODEL",
                "@cf/baai/bge-m3",
            ),
            dimensions=int(os.getenv("CF_ARCHIVE_VECTOR_DIMENSIONS", "1024")),
            timeout_seconds=float(os.getenv("CF_ARCHIVE_SEMANTIC_TIMEOUT_SECONDS", "6")),
            min_score=float(os.getenv("CF_ARCHIVE_SEMANTIC_MIN_SCORE", "0.45")),
        )

    @property
    def enabled(self) -> bool:
        return self.configured and not self._blocked_reason

    @staticmethod
    def namespace(owner_user_id: int) -> str:
        return f"u{int(owner_user_id)}"

    def _api(self, suffix: str) -> str:
        return (
            "https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/{suffix.lstrip('/')}"
        )

    async def _json_request(
        self,
        method: str,
        url: str,
        *,
        token: str,
        json_body: dict[str, Any] | None = None,
        file_body: bytes | None = None,
        allow_404: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        headers = {"Authorization": f"Bearer {token}"}
        request_kwargs: dict[str, Any] = {}
        if file_body is not None:
            form = aiohttp.FormData()
            form.add_field(
                "body",
                file_body,
                filename="vectors.ndjson",
                content_type="application/x-ndjson",
            )
            request_kwargs["data"] = form
        else:
            headers["Content-Type"] = "application/json"
            request_kwargs["json"] = json_body

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=headers,
                **request_kwargs,
            ) as response:
                status = response.status
                try:
                    body = await response.json()
                except Exception:
                    body = {}

        if allow_404 and status == 404:
            return status, body

        if status in {401, 403}:
            self._blocked_reason = f"permission_{status}"
            raise SemanticUnavailable(
                "Cloudflare Vectorize permission is missing or invalid."
            )
        if status >= 400:
            errors = body.get("errors") if isinstance(body, dict) else None
            raise SemanticUnavailable(
                f"Cloudflare request failed ({status}): {str(errors or body)[:180]}"
            )
        return status, body

    async def _embed(self, text: str) -> list[float]:
        if not self.enabled:
            raise SemanticUnavailable(self._blocked_reason or "Semantic index disabled.")

        _, body = await self._json_request(
            "POST",
            self._api(f"ai/run/{self.embedding_model}"),
            token=self.ai_token,
            json_body={"text": [text[:12000]]},
        )
        result = body.get("result", body) if isinstance(body, dict) else {}
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list) or not data or not isinstance(data[0], list):
            raise SemanticUnavailable("Workers AI embedding response had no vector.")
        vector = [float(value) for value in data[0]]
        if len(vector) != self.dimensions:
            raise SemanticUnavailable(
                f"Embedding dimensions {len(vector)} != index dimensions {self.dimensions}."
            )
        return vector

    async def ensure_index(self) -> bool:
        if not self.enabled:
            return False
        if self._index_ready:
            return True

        status, _ = await self._json_request(
            "GET",
            self._api(f"vectorize/v2/indexes/{self.index_name}"),
            token=self.vectorize_token,
            allow_404=True,
        )
        if status == 404:
            await self._json_request(
                "POST",
                self._api("vectorize/v2/indexes"),
                token=self.vectorize_token,
                json_body={
                    "name": self.index_name,
                    "description": "Derived semantic index for Asumi Archive",
                    "config": {
                        "dimensions": self.dimensions,
                        "metric": "cosine",
                    },
                },
            )
        self._index_ready = True
        return True

    @staticmethod
    def document_text(item: dict[str, Any]) -> str:
        metadata = item.get("metadata") or {}
        parts = [
            item.get("source_content") or "",
            item.get("source_author_name") or "",
            item.get("note") or "",
            item.get("source_url") or "",
        ]
        for embed in metadata.get("embeds") or []:
            parts.extend([
                embed.get("title") or "",
                embed.get("description") or "",
            ])
        for attachment in metadata.get("attachments") or []:
            parts.append(attachment.get("filename") or "")
        return "\n".join(part for part in parts if part).strip()[:12000]

    async def upsert_item(self, item: dict[str, Any]) -> bool:
        if not self.enabled:
            return False
        try:
            await self.ensure_index()
            text = self.document_text(item)
            if not text:
                return False
            vector = await self._embed(text)
            payload = {
                "id": str(int(item["id"])),
                "values": vector,
                "namespace": self.namespace(int(item["owner_user_id"])),
                "metadata": {
                    "archive_id": int(item["id"]),
                    "kind": str(item.get("source_kind") or "message")[:32],
                },
            }
            ndjson = json.dumps(payload, ensure_ascii=False) + "\n"
            await self._json_request(
                "POST",
                self._api(
                    f"vectorize/v2/indexes/{self.index_name}/upsert"
                ),
                token=self.vectorize_token,
                file_body=ndjson.encode("utf-8"),
            )
            return True
        except SemanticUnavailable as exc:
            print(f"⚠️ [Asumi Archive Semantic] upsert skipped: {exc}", flush=True)
            return False
        except Exception as exc:
            print(
                f"⚠️ [Asumi Archive Semantic] upsert error: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )
            return False

    async def query(
        self,
        owner_user_id: int,
        query: str,
        *,
        top_k: int = 8,
    ) -> list[SemanticMatch]:
        if not self.enabled or not (query or "").strip():
            return []
        try:
            await self.ensure_index()
            vector = await self._embed(query)
            _, body = await self._json_request(
                "POST",
                self._api(
                    f"vectorize/v2/indexes/{self.index_name}/query"
                ),
                token=self.vectorize_token,
                json_body={
                    "vector": vector,
                    "topK": max(1, min(int(top_k), 20)),
                    "namespace": self.namespace(owner_user_id),
                    "returnMetadata": "all",
                    "returnValues": False,
                },
            )
            result = body.get("result", body) if isinstance(body, dict) else {}
            matches = result.get("matches", []) if isinstance(result, dict) else []
            output: list[SemanticMatch] = []
            for match in matches:
                try:
                    score = float(match.get("score", 0.0))
                    archive_id = int(match.get("id"))
                except (TypeError, ValueError):
                    continue
                if score >= self.min_score:
                    output.append(SemanticMatch(archive_id=archive_id, score=score))
            return output
        except SemanticUnavailable as exc:
            print(f"⚠️ [Asumi Archive Semantic] query fallback: {exc}", flush=True)
            return []
        except Exception as exc:
            print(
                f"⚠️ [Asumi Archive Semantic] query error: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )
            return []

    async def delete_item(self, archive_id: int) -> bool:
        if not self.enabled:
            return False
        try:
            await self.ensure_index()
            await self._json_request(
                "POST",
                self._api(
                    f"vectorize/v2/indexes/{self.index_name}/delete_by_ids"
                ),
                token=self.vectorize_token,
                json_body={"ids": [str(int(archive_id))]},
            )
            return True
        except Exception as exc:
            print(
                f"⚠️ [Asumi Archive Semantic] delete skipped: "
                f"{type(exc).__name__}: {str(exc)[:160]}",
                flush=True,
            )
            return False


archive_semantic = ArchiveSemanticIndex.from_env()
