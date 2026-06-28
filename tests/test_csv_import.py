from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from decision_shelf.csv_import import preview_csv_import
from decision_shelf.database import Database
from decision_shelf.models import Card
from decision_shelf.webapp import create_app


class CsvImportTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "import.db")
        self.db.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_parses_bom_aliases_quoted_values_and_unknown_columns(self):
        content = (
            "\ufeff分类,title,总时长（分钟）,标签,精力要求,简介,额外列\n"
            '电影,"海边,一天",120,"剧情、治愈",低,"带逗号, 也能读取",忽略\n'
            "\n"
            "book,小王子,,经典;童话,medium,,忽略\n"
        )
        result = preview_csv_import(content, self.db)
        self.assertEqual(result["summary"], {"total": 2, "valid": 2, "duplicate": 0, "invalid": 0})
        first = result["rows"][0]
        self.assertEqual(first["row_number"], 2)
        self.assertEqual(first["draft"]["title"], "海边,一天")
        self.assertEqual(first["draft"]["tags"], ["剧情", "治愈"])
        self.assertEqual(first["draft"]["energy_level"], "low")
        self.assertIn("description", first["provided_fields"])
        self.assertEqual(result["warnings"], ["已忽略未知列：额外列"])

    def test_reports_invalid_and_duplicate_rows_without_writing(self):
        self.db.add_card(Card(id="movie_existing", category="movie", title="已存在"))
        content = (
            "category,title,priority,duration_minutes\n"
            "movie,已存在,3,90\n"
            "book,重复标题,3,\n"
            "book,重 复 标题,3,\n"
            "game,坏数据,9,-1\n"
            "unknown,无效分类,3,\n"
        )
        before = len(self.db.list_cards())
        result = preview_csv_import(content, self.db)
        self.assertEqual(result["summary"], {"total": 5, "valid": 1, "duplicate": 2, "invalid": 2})
        self.assertEqual(result["rows"][0]["existing_card"]["id"], "movie_existing")
        self.assertIn("文件中前面的卡片重复", result["rows"][2]["errors"][0])
        self.assertGreaterEqual(len(result["rows"][3]["errors"]), 2)
        self.assertEqual(len(self.db.list_cards()), before)

    def test_rejects_missing_headers_and_more_than_fifty_rows(self):
        with self.assertRaisesRegex(ValueError, "缺少必填列"):
            preview_csv_import("标题\n只有标题\n", self.db)
        too_many = "category,title\n" + "".join(f"movie,电影{i}\n" for i in range(51))
        with self.assertRaisesRegex(ValueError, "最多导入 50"):
            preview_csv_import(too_many, self.db)

    def test_rejects_oversized_or_non_utf8_decoded_content(self):
        oversized = "category,title\nmovie," + ("中" * 90000)
        with self.assertRaisesRegex(ValueError, "256 KB"):
            preview_csv_import(oversized, self.db)
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            preview_csv_import("category,title\nmovie,坏\ufffd标题\n", self.db)


class CsvImportApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "api-import.db")
        self.client = TestClient(create_app(self.db, static_dir=Path(self.temp.name) / "missing"))

    def tearDown(self):
        self.temp.cleanup()

    def test_preview_and_import_valid_rows(self):
        preview = self.client.post("/api/cards/import/preview", json={
            "filename": "cards.csv",
            "content": "分类,标题,标签\n电影,新电影,科幻、冒险\n游戏,,动作\n",
        })
        self.assertEqual(preview.status_code, 200)
        body = preview.json()
        self.assertEqual(body["summary"]["valid"], 1)
        self.assertEqual(body["summary"]["invalid"], 1)
        self.assertEqual(self.db.list_cards(), [])

        row = body["rows"][0]
        imported = self.client.post("/api/cards/import", json={"items": [{
            "row_number": row["row_number"],
            "draft": row["draft"],
        }]})
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(imported.json()["summary"], {"created": 1, "skipped": 0, "failed": 0})
        self.assertEqual(self.db.list_cards()[0].status, "todo")

    def test_commit_rechecks_title_and_external_duplicates(self):
        draft = {
            "category": "movie", "title": "竞态电影", "source": "tmdb", "external_id": "42",
            "description": "", "image_url": None, "duration_minutes": None,
            "min_session_minutes": None, "tags": [], "energy_level": "medium",
            "mood_fit": [], "notes": "", "priority": 3, "extension": {},
        }
        first = self.client.post("/api/cards/import", json={"items": [{"row_number": 2, "draft": draft}]})
        second = self.client.post("/api/cards/import", json={"items": [
            {"row_number": 2, "draft": {**draft, "title": "另一个译名"}},
            {"row_number": 3, "draft": {**draft, "source": "manual", "external_id": None}},
        ]})
        self.assertEqual(first.json()["summary"]["created"], 1)
        self.assertEqual(second.json()["summary"], {"created": 0, "skipped": 2, "failed": 0})
        self.assertEqual(len(self.db.list_cards()), 1)


if __name__ == "__main__":
    unittest.main()
