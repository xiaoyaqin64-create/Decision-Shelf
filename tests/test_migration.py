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
            connection.execute(
                """INSERT INTO cards(id,category,title,status,created_at,updated_at,rating)
                   VALUES ('done','book','旧完成卡','completed','2026-02-01','2026-03-04',4)"""
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
            self.assertIn("rating_score", columns)
            self.assertEqual(version, "5")
            completed = db.get_card("done")
            self.assertEqual(completed.rating, 8.0)
            self.assertEqual(completed.completed_at, "2026-03-04")
            self.assertTrue(completed.extension["completed_at_inferred"])

    def test_v4_ratings_and_interactions_are_scaled_to_ten_points(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "v4.db"
            db = Database(path)
            db.initialize()
            with db.connect() as connection:
                connection.execute(
                    """INSERT INTO cards(id,category,title,normalized_title,status,created_at,updated_at,rating)
                       VALUES ('rated','movie','旧评分','旧评分','completed','2026-01-01','2026-02-03',4)"""
                )
                connection.execute(
                    """INSERT INTO interactions(card_id,action,created_at,rating)
                       VALUES ('rated','complete','2026-02-03',3)"""
                )
                connection.execute("UPDATE cards SET rating_score=NULL WHERE id='rated'")
                connection.execute("UPDATE interactions SET rating_score=NULL WHERE card_id='rated'")
                connection.execute("UPDATE schema_meta SET value='4' WHERE key='version'")
            db.initialize()
            self.assertEqual(db.get_card("rated").rating, 8.0)
            with db.connect() as connection:
                score = connection.execute("SELECT rating_score FROM interactions WHERE card_id='rated'").fetchone()[0]
            self.assertEqual(score, 6.0)
            self.assertTrue(list(Path(folder).glob("v4.db.v4-*.bak")))


if __name__ == "__main__": unittest.main()
