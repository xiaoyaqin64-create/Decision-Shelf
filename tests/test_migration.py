from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from decision_shelf.database import Database


LEGACY_SCHEMA = """
CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO schema_meta VALUES ('version','1');
CREATE TABLE cards (
 id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL,
 duration_minutes INTEGER, min_session_minutes INTEGER, tags_json TEXT NOT NULL DEFAULT '[]',
 energy_level TEXT NOT NULL DEFAULT 'medium', mood_fit_json TEXT NOT NULL DEFAULT '[]',
 source TEXT NOT NULL DEFAULT 'manual', notes TEXT NOT NULL DEFAULT '', priority INTEGER NOT NULL DEFAULT 3,
 is_prioritized INTEGER NOT NULL DEFAULT 0, extension_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, last_recommended_at TEXT, completed_at TEXT, rating INTEGER, review TEXT
);
CREATE TABLE decision_sessions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, available_minutes INTEGER NOT NULL,
 energy_level TEXT NOT NULL, categories_json TEXT NOT NULL, preferences_json TEXT NOT NULL,
 moods_json TEXT NOT NULL, free_text TEXT NOT NULL DEFAULT '', normalized_context_json TEXT NOT NULL DEFAULT '{}',
 primary_card_id TEXT, recommendation_json TEXT NOT NULL DEFAULT '[]'
);
"""


class MigrationTestCase(unittest.TestCase):
    def test_v1_database_is_backed_up_and_migrated(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.executescript(LEGACY_SCHEMA)
            connection.execute(
                """INSERT INTO cards(id,category,title,status,created_at,updated_at)
                   VALUES ('old','movie','旧卡片','todo','2026-01-01','2026-01-01')"""
            )
            connection.commit()
            connection.close()
            db = Database(path)
            db.initialize()
            self.assertEqual(db.get_card("old").title, "旧卡片")
            self.assertTrue(list(Path(folder).glob("legacy.db.v1-*.bak")))
            with db.connect() as migrated:
                columns = {row["name"] for row in migrated.execute("PRAGMA table_info(cards)")}
                version = migrated.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()[0]
            self.assertIn("external_id", columns)
            self.assertIn("normalized_title", columns)
            self.assertIn("theme_color", columns)
            self.assertIn("theme_color_source", columns)
            self.assertEqual(version, "4")


if __name__ == "__main__": unittest.main()
