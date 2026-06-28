from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decision_shelf.database import Database
from decision_shelf.metadata.base import MetadataProvider
from decision_shelf.metadata.providers import OpenLibraryProvider, TMDbProvider
from decision_shelf.metadata.service import MetadataService
from decision_shelf.models import CardDraft, MetadataCandidate


class FakeProvider(MetadataProvider):
    source = "fake"
    category = "movie"

    def __init__(self):
        self.search_calls = 0
        self.draft_calls = 0

    @property
    def available(self):
        return True

    def search(self, query: str, limit: int = 8):
        self.search_calls += 1
        return [
            MetadataCandidate(
                source="fake", external_id="1", category="movie", title=query,
                raw={"id": "1", "title": query},
            )
        ]

    def draft(self, external_id: str, hint=None):
        self.draft_calls += 1
        return CardDraft(category="movie", title=hint["title"], source="fake", external_id=external_id)


class Registry:
    def __init__(self, provider): self.provider = provider
    def get(self, category): return self.provider
    def status(self): return {"movie": {"source": "fake", "available": True, "reason": None}}


class MetadataTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "metadata.db")
        self.db.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_service_caches_search_and_draft(self):
        provider = FakeProvider()
        service = MetadataService(self.db, Registry(provider))
        self.assertEqual(service.search("movie", "盗梦空间")[0].external_id, "1")
        self.assertEqual(service.search("movie", "盗梦空间")[0].external_id, "1")
        self.assertEqual(provider.search_calls, 1)
        self.assertEqual(service.draft("movie", "1").title, "盗梦空间")
        self.assertEqual(service.draft("movie", "1").title, "盗梦空间")
        self.assertEqual(provider.draft_calls, 1)

    def test_tmdb_maps_search_and_detail(self):
        import httpx

        def handler(request):
            if request.url.path.endswith("/search/movie"):
                return httpx.Response(200, json={"results": [{"id": 10, "title": "盗梦空间", "original_title": "Inception", "release_date": "2010-07-16", "poster_path": "/p.jpg", "overview": "梦境冒险"}]})
            return httpx.Response(200, json={"id": 10, "title": "盗梦空间", "original_title": "Inception", "release_date": "2010-07-16", "runtime": 148, "overview": "梦境冒险", "poster_path": "/p.jpg", "genres": [{"name": "科幻"}], "production_countries": [{"name": "美国"}], "credits": {"crew": [{"job": "Director", "name": "诺兰"}]}, "vote_average": 8.7})

        provider = TMDbProvider(token="token", transport=httpx.MockTransport(handler))
        candidate = provider.search("盗梦空间")[0]
        draft = provider.draft(candidate.external_id, candidate.raw)
        self.assertEqual(candidate.year, 2010)
        self.assertEqual(draft.duration_minutes, 148)
        self.assertEqual(draft.extension["director"], "诺兰")
        self.assertIn("科幻", draft.tags)

    def test_openlibrary_maps_book_without_inventing_duration(self):
        import httpx

        def handler(request):
            if request.url.path == "/search.json":
                return httpx.Response(200, json={"docs": [{"key": "/works/OL1W", "title": "小王子", "author_name": ["圣埃克苏佩里"], "first_publish_year": 1943, "cover_i": 99, "number_of_pages_median": 120}]})
            return httpx.Response(200, json={"title": "小王子", "description": "一则寓言", "subjects": ["经典", "文学"], "covers": [99]})

        provider = OpenLibraryProvider(transport=httpx.MockTransport(handler))
        candidate = provider.search("小王子")[0]
        draft = provider.draft(candidate.external_id, candidate.raw)
        self.assertIsNone(draft.duration_minutes)
        self.assertEqual(draft.min_session_minutes, 25)
        self.assertEqual(draft.extension["author"], "圣埃克苏佩里")


if __name__ == "__main__": unittest.main()
