from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from decision_shelf.backup import BackupError, BackupService
from decision_shelf.database import Database
from decision_shelf.webapp import create_app


class BackupTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "decision_shelf.db")
        self.client = TestClient(
            create_app(self.db, static_dir=self.root / "missing-frontend")
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_export_and_restore_replace_all_data(self):
        first = self.client.post(
            "/api/cards", json={"category": "book", "title": "备份里的书"}
        )
        self.assertEqual(first.status_code, 201)
        exported = self.client.get("/api/backup/export")
        self.assertEqual(exported.status_code, 200)
        self.assertTrue(exported.content.startswith(b"SQLite format 3\x00"))
        self.assertNotIn(b"DEEPSEEK_API_KEY", exported.content)

        self.client.post(
            "/api/cards", json={"category": "movie", "title": "恢复后应消失"}
        )
        restored = self.client.post(
            "/api/backup/restore",
            content=exported.content,
            headers={"content-type": "application/x-sqlite3"},
        )
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["cards"], 1)
        cards = self.client.get("/api/cards").json()["items"]
        self.assertEqual([item["title"] for item in cards], ["备份里的书"])
        self.assertTrue(list(self.root.glob("decision_shelf.pre-restore-*.bak")))

    def test_invalid_restore_preserves_live_database(self):
        self.client.post(
            "/api/cards", json={"category": "album", "title": "不能丢失"}
        )
        response = self.client.post(
            "/api/backup/restore", content=b"not a sqlite backup"
        )
        self.assertEqual(response.status_code, 422)
        cards = self.client.get("/api/cards").json()["items"]
        self.assertEqual([item["title"] for item in cards], ["不能丢失"])

    def test_newer_schema_is_rejected(self):
        snapshot = BackupService(self.db).create_snapshot()
        with closing(sqlite3.connect(snapshot)) as connection:
            connection.execute(
                "UPDATE schema_meta SET value='999' WHERE key='version'"
            )
            connection.commit()
        with self.assertRaisesRegex(BackupError, "更新版本"):
            BackupService(self.db).validate(snapshot)
        snapshot.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
