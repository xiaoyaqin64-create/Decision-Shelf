from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from decision_shelf.database import Database
from decision_shelf.models import Card
from decision_shelf.theme_color import ThemeColorService, extract_theme_color, fallback_color, is_allowed_image_url


def image_bytes(color: tuple[int, int, int]) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (30, 30), color).save(output, format="PNG")
    return output.getvalue()


class ThemeColorTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "colors.db")
        self.db.initialize()

    def tearDown(self): self.temp.cleanup()

    def test_extracts_and_darkens_dominant_color(self):
        color = extract_theme_color(image_bytes((220, 50, 70)))
        self.assertRegex(color, r"^#[0-9A-F]{6}$")
        self.assertNotEqual(color, "#DC3246")

    def test_allowed_hosts_and_untrusted_url(self):
        self.assertTrue(is_allowed_image_url("https://image.tmdb.org/t/p/w500/a.jpg"))
        self.assertTrue(is_allowed_image_url("https://ia800.example.archive.org/a.jpg"))
        self.assertFalse(is_allowed_image_url("http://image.tmdb.org/a.jpg"))
        self.assertFalse(is_allowed_image_url("https://127.0.0.1/a.jpg"))

    def test_resolve_caches_extracted_color(self):
        card = Card(id="movie", category="movie", title="红色电影", image_url="https://image.tmdb.org/t/p/w500/a.jpg")
        self.db.add_card(card)
        calls = []
        service = ThemeColorService(self.db, fetcher=lambda url: calls.append(url) or image_bytes((180, 40, 60)))
        first = service.resolve(self.db.get_card("movie"))
        second = service.resolve(self.db.get_card("movie"))
        self.assertEqual(first["source"], "extracted")
        self.assertEqual(first["theme_color"], second["theme_color"])
        self.assertEqual(len(calls), 1)

    def test_missing_or_untrusted_image_uses_stable_fallback(self):
        card = Card(id="book", category="book", title="没有封面", image_url="https://evil.example/a.jpg")
        self.db.add_card(card)
        result = ThemeColorService(self.db, fetcher=lambda _url: (_ for _ in ()).throw(AssertionError())).resolve(card)
        self.assertEqual(result["source"], "fallback")
        self.assertEqual(result["theme_color"], fallback_color("book", "没有封面"))

    def test_image_change_resets_color_to_pending(self):
        card = Card(id="album", category="album", title="专辑", image_url="https://coverartarchive.org/a.jpg")
        self.db.add_card(card)
        self.db.set_theme_color(card.id, "#334455", "extracted")
        updated = self.db.get_card(card.id)
        updated.image_url = "https://coverartarchive.org/b.jpg"
        self.db.update_card(updated)
        changed = self.db.get_card(card.id)
        self.assertIsNone(changed.theme_color)
        self.assertEqual(changed.theme_color_source, "pending")


if __name__ == "__main__": unittest.main()
