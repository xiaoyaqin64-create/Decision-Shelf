from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from ..database import Database
from ..models import CardDraft, MetadataCandidate
from ..utils import now_local
from .base import MetadataError
from .providers import ProviderRegistry


class MetadataService:
    def __init__(self, database: Database, registry: ProviderRegistry | None = None):
        self.database = database
        self.registry = registry or ProviderRegistry()

    def search(self, category: str, query: str, limit: int = 8) -> list[MetadataCandidate]:
        query = query.strip()
        if len(query) < 2:
            raise MetadataError(
                "query_too_short", "请至少输入两个字符", status_code=422
            )
        provider = self.registry.get(category)
        key = f"search:{query.casefold()}:{limit}"
        cached = self.database.get_cache(provider.source, key)
        if cached:
            return [MetadataCandidate(**item) for item in cached.get("items", [])]
        items = provider.search(query, limit)
        expires = (now_local() + timedelta(hours=24)).isoformat(timespec="seconds")
        self.database.set_cache(
            provider.source,
            key,
            {"items": [asdict(item) for item in items]},
            expires_at=expires,
        )
        detail_expiry = (now_local() + timedelta(days=7)).isoformat(timespec="seconds")
        for item in items:
            self.database.set_cache(
                provider.source,
                f"hint:{item.external_id}",
                item.raw,
                expires_at=detail_expiry,
            )
        return items

    def draft(self, category: str, external_id: str) -> CardDraft:
        provider = self.registry.get(category)
        key = f"draft:{external_id}"
        cached = self.database.get_cache(provider.source, key)
        if cached:
            return CardDraft(**cached)
        hint = self.database.get_cache(provider.source, f"hint:{external_id}") or {}
        draft = provider.draft(external_id, hint)
        expires = (now_local() + timedelta(days=7)).isoformat(timespec="seconds")
        self.database.set_cache(
            provider.source, key, asdict(draft), expires_at=expires
        )
        return draft

    def status(self) -> dict[str, dict[str, Any]]:
        return self.registry.status()
