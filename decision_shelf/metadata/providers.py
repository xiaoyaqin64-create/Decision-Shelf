from __future__ import annotations

import os
import threading
import time
from datetime import date
from typing import Any

from ..models import CardDraft, MetadataCandidate
from ..utils import normalize_terms
from .base import HttpProvider, MetadataError, MetadataProvider


def _year(value: Any) -> int | None:
    text = str(value or "")
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return None


def _description(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value or "")


class TMDbProvider(HttpProvider):
    source = "tmdb"
    category = "movie"
    base_url = "https://api.themoviedb.org/3"

    def __init__(self, token: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.token = (token if token is not None else os.getenv("TMDB_READ_ACCESS_TOKEN", "")).strip()

    @property
    def available(self) -> bool:
        return bool(self.token)

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.available else "缺少 TMDB_READ_ACCESS_TOKEN"

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def search(self, query: str, limit: int = 8) -> list[MetadataCandidate]:
        if not self.available:
            raise MetadataError("provider_not_configured", self.unavailable_reason or "TMDb 未配置", status_code=503)
        data = self._get_json(
            f"{self.base_url}/search/movie",
            params={"query": query, "language": "zh-CN", "include_adult": "false"},
            headers=self.headers,
        )
        candidates: list[MetadataCandidate] = []
        for item in data.get("results", [])[:limit]:
            poster = item.get("poster_path")
            candidates.append(
                MetadataCandidate(
                    source=self.source,
                    external_id=str(item.get("id")),
                    category=self.category,
                    title=item.get("title") or item.get("original_title") or query,
                    subtitle=item.get("original_title") or "",
                    year=_year(item.get("release_date")),
                    image_url=f"https://image.tmdb.org/t/p/w500{poster}" if poster else None,
                    description=item.get("overview") or "",
                    raw=item,
                )
            )
        return candidates

    def draft(self, external_id: str, hint: dict[str, Any] | None = None) -> CardDraft:
        data = self._get_json(
            f"{self.base_url}/movie/{external_id}",
            params={"language": "zh-CN", "append_to_response": "credits"},
            headers=self.headers,
        )
        crew = data.get("credits", {}).get("crew", [])
        directors = [item.get("name") for item in crew if item.get("job") == "Director"]
        genres = normalize_terms([item.get("name", "") for item in data.get("genres", [])])
        countries = normalize_terms(
            [item.get("name", "") for item in data.get("production_countries", [])]
        )
        poster = data.get("poster_path")
        return CardDraft(
            category="movie",
            title=data.get("title") or data.get("original_title") or (hint or {}).get("title", ""),
            source=self.source,
            external_id=str(data.get("id") or external_id),
            description=data.get("overview") or "",
            image_url=f"https://image.tmdb.org/t/p/w500{poster}" if poster else None,
            duration_minutes=data.get("runtime") or None,
            tags=genres,
            extension={
                "original_title": data.get("original_title"),
                "director": "、".join(filter(None, directors)),
                "year": _year(data.get("release_date")),
                "country": "、".join(countries),
                "tmdb_rating": data.get("vote_average"),
            },
        )


class OpenLibraryProvider(HttpProvider):
    source = "openlibrary"
    category = "book"

    @property
    def available(self) -> bool:
        return True

    def search(self, query: str, limit: int = 8) -> list[MetadataCandidate]:
        data = self._get_json(
            "https://openlibrary.org/search.json",
            params={
                "q": query,
                "limit": limit,
                "fields": "key,title,author_name,first_publish_year,cover_i,subject,number_of_pages_median,language",
            },
        )
        result: list[MetadataCandidate] = []
        for item in data.get("docs", [])[:limit]:
            key = str(item.get("key", "")).replace("/works/", "")
            if not key:
                continue
            authors = [str(value) for value in item.get("author_name", [])]
            cover_id = item.get("cover_i")
            result.append(
                MetadataCandidate(
                    source=self.source,
                    external_id=key,
                    category=self.category,
                    title=item.get("title") or query,
                    subtitle="、".join(authors[:3]),
                    year=item.get("first_publish_year"),
                    creators=authors,
                    image_url=(
                        f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
                        if cover_id
                        else None
                    ),
                    raw=item,
                )
            )
        return result

    def draft(self, external_id: str, hint: dict[str, Any] | None = None) -> CardDraft:
        hint = hint or {}
        data = self._get_json(f"https://openlibrary.org/works/{external_id}.json")
        subjects = normalize_terms([str(value) for value in data.get("subjects", [])])[:10]
        covers = data.get("covers", [])
        cover_id = (hint.get("cover_i") or (covers[0] if covers else None))
        authors = [str(value) for value in hint.get("author_name", [])]
        pages = hint.get("number_of_pages_median")
        return CardDraft(
            category="book",
            title=data.get("title") or hint.get("title") or external_id,
            source=self.source,
            external_id=external_id,
            description=_description(data.get("description")),
            image_url=(
                f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None
            ),
            min_session_minutes=25,
            tags=subjects,
            extension={
                "author": "、".join(authors),
                "year": hint.get("first_publish_year"),
                "pages": pages,
                "difficulty": "medium",
            },
        )


class MusicBrainzProvider(HttpProvider):
    source = "musicbrainz"
    category = "album"
    base_url = "https://musicbrainz.org/ws/2"
    _lock = threading.Lock()
    _last_request_at = 0.0

    def __init__(self, contact: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.contact = (contact if contact is not None else os.getenv("MUSICBRAINZ_CONTACT", "")).strip()

    @property
    def available(self) -> bool:
        return bool(self.contact)

    @property
    def unavailable_reason(self) -> str | None:
        return None if self.available else "缺少 MUSICBRAINZ_CONTACT"

    @property
    def headers(self) -> dict[str, str]:
        return {"User-Agent": f"DecisionShelf/0.2 ({self.contact})", "Accept": "application/json"}

    def _musicbrainz_json(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise MetadataError("provider_not_configured", self.unavailable_reason or "MusicBrainz 未配置", status_code=503)
        with self._lock:
            wait = 1.05 - (time.monotonic() - self.__class__._last_request_at)
            if wait > 0:
                time.sleep(wait)
            result = self._get_json(
                f"{self.base_url}/{path}", params={**params, "fmt": "json"}, headers=self.headers
            )
            self.__class__._last_request_at = time.monotonic()
            return result

    @staticmethod
    def _artists(credit: list[dict[str, Any]]) -> list[str]:
        return normalize_terms(
            [str(item.get("name") or item.get("artist", {}).get("name") or "") for item in credit]
        )

    def search(self, query: str, limit: int = 8) -> list[MetadataCandidate]:
        data = self._musicbrainz_json(
            "release-group/",
            {"query": f'releasegroup:"{query}" AND primarytype:album', "limit": limit},
        )
        result: list[MetadataCandidate] = []
        for item in data.get("release-groups", [])[:limit]:
            artists = self._artists(item.get("artist-credit", []))
            external_id = item.get("id")
            if not external_id:
                continue
            result.append(
                MetadataCandidate(
                    source=self.source,
                    external_id=external_id,
                    category=self.category,
                    title=item.get("title") or query,
                    subtitle="、".join(artists),
                    year=_year(item.get("first-release-date")),
                    creators=artists,
                    image_url=f"https://coverartarchive.org/release-group/{external_id}/front-500",
                    raw=item,
                )
            )
        return result

    def draft(self, external_id: str, hint: dict[str, Any] | None = None) -> CardDraft:
        data = self._musicbrainz_json(
            f"release-group/{external_id}",
            {"inc": "artist-credits+genres+tags+releases"},
        )
        artists = self._artists(data.get("artist-credit", []))
        genres = normalize_terms(
            [item.get("name", "") for item in [*data.get("genres", []), *data.get("tags", [])]]
        )[:10]
        releases = data.get("releases", [])
        release = next((item for item in releases if item.get("status") == "Official"), None)
        release = release or (releases[0] if releases else None)
        duration: int | None = None
        if release and release.get("id"):
            detail = self._musicbrainz_json(
                f"release/{release['id']}", {"inc": "recordings"}
            )
            lengths = [
                track.get("length") or track.get("recording", {}).get("length") or 0
                for medium in detail.get("media", [])
                for track in medium.get("tracks", [])
            ]
            if any(lengths):
                duration = max(1, round(sum(lengths) / 60000))
        return CardDraft(
            category="album",
            title=data.get("title") or (hint or {}).get("title") or external_id,
            source=self.source,
            external_id=external_id,
            image_url=f"https://coverartarchive.org/release-group/{external_id}/front-500",
            duration_minutes=duration,
            tags=genres,
            extension={
                "artist": "、".join(artists),
                "year": _year(data.get("first-release-date")),
                "style": "、".join(genres),
                "musicbrainz_id": external_id,
            },
        )


class ProviderRegistry:
    def __init__(
        self,
        *,
        tmdb: MetadataProvider | None = None,
        openlibrary: MetadataProvider | None = None,
        musicbrainz: MetadataProvider | None = None,
    ):
        self.providers: dict[str, MetadataProvider] = {
            "movie": tmdb or TMDbProvider(),
            "book": openlibrary or OpenLibraryProvider(),
            "album": musicbrainz or MusicBrainzProvider(),
        }

    def get(self, category: str) -> MetadataProvider:
        provider = self.providers.get(category)
        if provider is None:
            raise MetadataError(
                "provider_unavailable",
                "该分类尚未接入外部元数据源",
                status_code=400,
            )
        return provider

    def status(self) -> dict[str, dict[str, Any]]:
        return {
            category: {
                "source": provider.source,
                "available": provider.available,
                "reason": provider.unavailable_reason,
            }
            for category, provider in self.providers.items()
        }

