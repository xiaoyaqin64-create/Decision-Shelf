from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from ..models import CardDraft, MetadataCandidate


class MetadataError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int = 502,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status_code = status_code


class MetadataProvider(ABC):
    source: str
    category: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.available else "服务尚未配置"

    @abstractmethod
    def search(self, query: str, limit: int = 8) -> list[MetadataCandidate]: ...

    @abstractmethod
    def draft(
        self, external_id: str, hint: dict[str, Any] | None = None
    ) -> CardDraft: ...


class HttpProvider(MetadataProvider):
    def __init__(self, *, timeout: float = 12.0, transport=None):
        self.client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self.client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise MetadataError(
                "provider_unreachable", f"外部数据源连接失败：{exc}", retryable=True
            ) from exc
        if response.status_code in {429, 500, 502, 503, 504}:
            raise MetadataError(
                "provider_busy",
                f"外部数据源暂时不可用（HTTP {response.status_code}）",
                retryable=True,
            )
        if response.status_code in {401, 403}:
            raise MetadataError(
                "provider_auth", "外部数据源凭据无效或权限不足", status_code=503
            )
        if response.status_code == 404:
            raise MetadataError("not_found", "没有找到对应的外部内容", status_code=404)
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPStatusError, ValueError) as exc:
            raise MetadataError("provider_response", "外部数据源返回了无效响应") from exc
        if not isinstance(payload, dict):
            raise MetadataError("provider_response", "外部数据源响应格式不正确")
        return payload

