from __future__ import annotations

import os
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .models import Candidate, Card, CardDraft, DecisionContext, ExplorationSuggestion
from .taxonomy import title_key
from .utils import iso_now, json_dumps, json_loads, parse_iso


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cards (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL CHECK (category IN ('movie','book','album','game')),
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'todo'
        CHECK (status IN ('todo','in_progress','completed','removed')),
    duration_minutes INTEGER,
    min_session_minutes INTEGER,
    tags_json TEXT NOT NULL DEFAULT '[]',
    energy_level TEXT NOT NULL DEFAULT 'medium'
        CHECK (energy_level IN ('low','medium','high')),
    mood_fit_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL DEFAULT 'manual',
    external_id TEXT,
    description TEXT NOT NULL DEFAULT '',
    image_url TEXT,
    theme_color TEXT,
    theme_color_source TEXT NOT NULL DEFAULT 'pending',
    notes TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    is_prioritized INTEGER NOT NULL DEFAULT 0,
    extension_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_recommended_at TEXT,
    completed_at TEXT,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review TEXT
);

CREATE TABLE IF NOT EXISTS decision_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    available_minutes INTEGER NOT NULL,
    energy_level TEXT NOT NULL,
    categories_json TEXT NOT NULL,
    preferences_json TEXT NOT NULL,
    moods_json TEXT NOT NULL,
    free_text TEXT NOT NULL DEFAULT '',
    normalized_context_json TEXT NOT NULL DEFAULT '{}',
    primary_card_id TEXT,
    recommendation_json TEXT NOT NULL DEFAULT '[]',
    decision_scope TEXT NOT NULL DEFAULT 'shelf_only',
    fallback_reason TEXT,
    eligible_count INTEGER NOT NULL DEFAULT 0,
    top_fit_score REAL,
    FOREIGN KEY (primary_card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS decision_candidates (
    session_id INTEGER NOT NULL,
    card_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    total_score REAL NOT NULL,
    score_json TEXT NOT NULL,
    adjustments_json TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (session_id, card_id),
    FOREIGN KEY (session_id) REFERENCES decision_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TEXT NOT NULL,
    decision_session_id INTEGER,
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    review TEXT,
    payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY (card_id) REFERENCES cards(id),
    FOREIGN KEY (decision_session_id) REFERENCES decision_sessions(id)
);

CREATE TABLE IF NOT EXISTS preference_weights (
    key_type TEXT NOT NULL,
    key TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0 CHECK (weight BETWEEN -5 AND 5),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (key_type, key)
);

CREATE TABLE IF NOT EXISTS exploration_suggestions (
    id TEXT PRIMARY KEY,
    session_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT,
    draft_json TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0,
    fit_score REAL NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    is_best INTEGER NOT NULL DEFAULT 0,
    resolution TEXT NOT NULL DEFAULT 'pending',
    resolved_card_id TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (session_id) REFERENCES decision_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (resolved_card_id) REFERENCES cards(id)
);

CREATE TABLE IF NOT EXISTS metadata_cache (
    provider TEXT NOT NULL,
    cache_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (provider, cache_key)
);

CREATE TABLE IF NOT EXISTS activity_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT NOT NULL,
    minutes INTEGER NOT NULL CHECK(minutes > 0),
    note TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL,
    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_enrichment_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id TEXT,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    error TEXT,
    added_tags_json TEXT NOT NULL DEFAULT '[]',
    added_moods_json TEXT NOT NULL DEFAULT '[]',
    retried INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_cards_status_category ON cards(status, category);
CREATE INDEX IF NOT EXISTS idx_interactions_card_action_time
    ON interactions(card_id, action, created_at);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON decision_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_exploration_session
    ON exploration_suggestions(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_exploration_identity
    ON exploration_suggestions(source, external_id, created_at);
CREATE INDEX IF NOT EXISTS idx_activity_card_time ON activity_sessions(card_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_enrichment_card_time ON ai_enrichment_logs(card_id, created_at);
"""


class Database:
    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("DECISION_SHELF_DB") or "data/decision_shelf.db"
        self.path = Path(configured)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self._backup_before_migration()
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            self._ensure_v4(connection)
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('version', '4')"
            )

    def _backup_before_migration(self) -> Path | None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            return None
        try:
            connection = sqlite3.connect(self.path)
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
            connection.close()
            version = int(row[0]) if row else 1
        except (sqlite3.Error, ValueError):
            version = 1
        if version >= 4:
            return None
        timestamp = iso_now().replace(":", "-")
        backup = self.path.with_name(f"{self.path.name}.v{version}-{timestamp}.bak")
        shutil.copy2(self.path, backup)
        return backup

    @staticmethod
    def _ensure_v4(connection: sqlite3.Connection) -> None:
        additions = {
            "cards": {
                "external_id": "TEXT",
                "description": "TEXT NOT NULL DEFAULT ''",
                "image_url": "TEXT",
                "normalized_title": "TEXT NOT NULL DEFAULT ''",
                "theme_color": "TEXT",
                "theme_color_source": "TEXT NOT NULL DEFAULT 'pending'",
            },
            "decision_sessions": {
                "decision_scope": "TEXT NOT NULL DEFAULT 'shelf_only'",
                "fallback_reason": "TEXT",
                "eligible_count": "INTEGER NOT NULL DEFAULT 0",
                "top_fit_score": "REAL",
            },
            "exploration_suggestions": {"is_best": "INTEGER NOT NULL DEFAULT 0"},
        }
        for table, columns in additions.items():
            existing = {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS activity_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT NOT NULL,
                minutes INTEGER NOT NULL CHECK(minutes > 0), note TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL, FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE CASCADE);
            CREATE TABLE IF NOT EXISTS ai_enrichment_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, card_id TEXT, category TEXT NOT NULL,
                title TEXT NOT NULL, status TEXT NOT NULL, model TEXT, error TEXT,
                added_tags_json TEXT NOT NULL DEFAULT '[]', added_moods_json TEXT NOT NULL DEFAULT '[]',
                retried INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                FOREIGN KEY(card_id) REFERENCES cards(id) ON DELETE SET NULL);
            """
        )
        rows = connection.execute("SELECT id,title FROM cards").fetchall()
        for row in rows:
            connection.execute("UPDATE cards SET normalized_title=? WHERE id=?", (title_key(row["title"]), row["id"]))
        Database._merge_duplicate_titles(connection)
        connection.executescript("""
            DROP INDEX IF EXISTS idx_cards_external_unique;
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_external_unique ON cards(source, external_id)
                WHERE external_id IS NOT NULL AND external_id != '';
            CREATE UNIQUE INDEX IF NOT EXISTS idx_cards_title_unique ON cards(category, normalized_title)
                WHERE normalized_title != '';
            CREATE INDEX IF NOT EXISTS idx_activity_card_time ON activity_sessions(card_id, recorded_at);
            CREATE INDEX IF NOT EXISTS idx_enrichment_card_time ON ai_enrichment_logs(card_id, created_at);
        """)

    @staticmethod
    def _merge_duplicate_titles(connection: sqlite3.Connection) -> None:
        groups = connection.execute("""SELECT category,normalized_title,GROUP_CONCAT(id) ids,COUNT(*) count
            FROM cards WHERE normalized_title!='' GROUP BY category,normalized_title HAVING COUNT(*)>1""").fetchall()
        for group in groups:
            ids = str(group["ids"]).split(",")
            rows = connection.execute(f"SELECT * FROM cards WHERE id IN ({','.join('?' for _ in ids)})", ids).fetchall()
            rank = {"completed": 4, "in_progress": 3, "todo": 2, "removed": 1}
            survivor = max(rows, key=lambda r: (rank.get(r["status"], 0), bool(r["external_id"]), len(r["description"] or ""), -(ids.index(r["id"]))))
            keep = survivor["id"]
            for duplicate in rows:
                old = duplicate["id"]
                if old == keep: continue
                current = connection.execute("SELECT * FROM cards WHERE id=?", (keep,)).fetchone()
                tags = list(dict.fromkeys([*json_loads(current["tags_json"], []), *json_loads(duplicate["tags_json"], [])]))
                moods = list(dict.fromkeys([*json_loads(current["mood_fit_json"], []), *json_loads(duplicate["mood_fit_json"], [])]))
                extension = {**json_loads(duplicate["extension_json"], {}), **json_loads(current["extension_json"], {})}
                description = max((current["description"] or "", duplicate["description"] or ""), key=len)
                notes = max((current["notes"] or "", duplicate["notes"] or ""), key=len)
                external_id = current["external_id"] or duplicate["external_id"]
                connection.execute("""UPDATE cards SET duration_minutes=?,min_session_minutes=?,tags_json=?,mood_fit_json=?,
                    source=?,external_id=?,description=?,image_url=?,notes=?,priority=?,extension_json=? WHERE id=?""", (
                    current["duration_minutes"] or duplicate["duration_minutes"], current["min_session_minutes"] or duplicate["min_session_minutes"],
                    json_dumps(tags), json_dumps(moods), current["source"] if current["external_id"] else duplicate["source"], external_id,
                    description, current["image_url"] or duplicate["image_url"], notes, max(current["priority"], duplicate["priority"]), json_dumps(extension), keep))
                connection.execute("UPDATE interactions SET card_id=? WHERE card_id=?", (keep, old))
                connection.execute("UPDATE decision_sessions SET primary_card_id=? WHERE primary_card_id=?", (keep, old))
                connection.execute("UPDATE exploration_suggestions SET resolved_card_id=? WHERE resolved_card_id=?", (keep, old))
                connection.execute("UPDATE activity_sessions SET card_id=? WHERE card_id=?", (keep, old))
                conflicts = connection.execute("SELECT session_id FROM decision_candidates WHERE card_id=?", (old,)).fetchall()
                for item in conflicts:
                    exists = connection.execute("SELECT 1 FROM decision_candidates WHERE session_id=? AND card_id=?", (item["session_id"], keep)).fetchone()
                    if exists: connection.execute("DELETE FROM decision_candidates WHERE session_id=? AND card_id=?", (item["session_id"], old))
                    else: connection.execute("UPDATE decision_candidates SET card_id=? WHERE session_id=? AND card_id=?", (keep, item["session_id"], old))
                connection.execute("DELETE FROM cards WHERE id=?", (old,))

    def add_card(self, card: Card, *, replace: bool = False) -> None:
        card.validate()
        timestamp = iso_now()
        card.created_at = card.created_at or timestamp
        card.updated_at = timestamp
        verb = "INSERT OR REPLACE" if replace else "INSERT"
        with self.connect() as connection:
            connection.execute(
                f"""{verb} INTO cards (
                    id, category, title, normalized_title, status, duration_minutes, min_session_minutes,
                    tags_json, energy_level, mood_fit_json, source, external_id,
                    description, image_url, theme_color, theme_color_source, notes, priority,
                    is_prioritized, extension_json, created_at, updated_at,
                    last_recommended_at, completed_at, rating, review
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                self._card_values(card),
            )

    def update_card(self, card: Card) -> None:
        card.validate()
        card.updated_at = iso_now()
        with self.connect() as connection:
            old = connection.execute("SELECT image_url FROM cards WHERE id=?", (card.id,)).fetchone()
            if old and old["image_url"] != card.image_url:
                card.theme_color = None
                card.theme_color_source = "pending"
            cursor = connection.execute(
                """UPDATE cards SET
                    category=?, title=?, normalized_title=?, status=?, duration_minutes=?, min_session_minutes=?,
                    tags_json=?, energy_level=?, mood_fit_json=?, source=?, notes=?, priority=?,
                    external_id=?, description=?, image_url=?, theme_color=?, theme_color_source=?, is_prioritized=?,
                    extension_json=?, updated_at=?, last_recommended_at=?,
                    completed_at=?, rating=?, review=? WHERE id=?""",
                (
                    card.category,
                    card.title,
                    title_key(card.title),
                    card.status,
                    card.duration_minutes,
                    card.min_session_minutes,
                    json_dumps(card.tags),
                    card.energy_level,
                    json_dumps(card.mood_fit),
                    card.source,
                    card.notes,
                    card.priority,
                    card.external_id,
                    card.description,
                    card.image_url,
                    card.theme_color,
                    card.theme_color_source,
                    int(card.is_prioritized),
                    json_dumps(card.extension),
                    card.updated_at,
                    card.last_recommended_at,
                    card.completed_at,
                    card.rating,
                    card.review,
                    card.id,
                ),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"没有找到卡片：{card.id}")

    def get_card(self, card_id: str) -> Card | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
        return self._row_to_card(row) if row else None

    def list_cards(
        self,
        *,
        category: str | None = None,
        status: str | None = None,
        query: str | None = None,
    ) -> list[Card]:
        conditions: list[str] = []
        params: list[Any] = []
        if category:
            conditions.append("category=?")
            params.append(category)
        if status:
            conditions.append("status=?")
            params.append(status)
        if query:
            conditions.append(
                "(title LIKE ? OR tags_json LIKE ? OR notes LIKE ? OR description LIKE ?)"
            )
            pattern = f"%{query.strip()}%"
            params.extend([pattern, pattern, pattern, pattern])
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM cards {where} ORDER BY category, status, priority DESC, created_at",
                params,
            ).fetchall()
        return [self._row_to_card(row) for row in rows]

    def find_by_external(self, source: str, external_id: str) -> Card | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM cards WHERE source=? AND external_id=? LIMIT 1",
                (source, external_id),
            ).fetchone()
        return self._row_to_card(row) if row else None

    def find_by_title(self, category: str, title: str) -> Card | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cards WHERE category=? AND normalized_title=? LIMIT 1", (category, title_key(title))).fetchone()
        return self._row_to_card(row) if row else None

    def set_theme_color(self, card_id: str, color: str, source: str) -> Card:
        if source not in {"extracted", "fallback"}:
            raise ValueError("主题色来源必须是 extracted 或 fallback")
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE cards SET theme_color=?,theme_color_source=?,updated_at=? WHERE id=?",
                (color, source, iso_now(), card_id),
            )
            if not cursor.rowcount:
                raise KeyError(f"没有找到卡片：{card_id}")
        card = self.get_card(card_id)
        assert card is not None
        return card

    def upsert_card(self, incoming: Card) -> tuple[Card, str]:
        existing = self.find_by_external(incoming.source, incoming.external_id) if incoming.external_id else None
        existing = existing or self.find_by_title(incoming.category, incoming.title)
        if not existing:
            self.add_card(incoming)
            return incoming, "created"
        # 覆盖资料，但明确保留进度、完成反馈、历史关联和累计时长。
        preserved = {name: getattr(existing, name) for name in (
            "id", "status", "created_at", "last_recommended_at", "completed_at", "rating", "review", "is_prioritized")}
        for name in ("title", "duration_minutes", "min_session_minutes", "tags", "energy_level", "mood_fit", "source", "external_id", "description", "image_url", "notes", "priority", "extension"):
            value = getattr(incoming, name)
            if value not in (None, "", [], {}): setattr(existing, name, value)
        for name, value in preserved.items(): setattr(existing, name, value)
        self.update_card(existing)
        return existing, "overwritten"

    def restore_card(self, card_id: str) -> Card:
        card = self.get_card(card_id)
        if not card: raise KeyError(f"没有找到卡片：{card_id}")
        if card.status != "removed": raise ValueError("只有回收站中的卡片可以恢复")
        card.status = "todo"; self.update_card(card)
        self.add_interaction(card.id, "restore")
        return card

    def permanent_delete_card(self, card_id: str) -> None:
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM cards WHERE id=?", (card_id,)).fetchone()
            if not row: raise KeyError(f"没有找到卡片：{card_id}")
            if row["status"] != "removed": raise ValueError("请先将卡片移入回收站")
            connection.execute("UPDATE decision_sessions SET primary_card_id=NULL WHERE primary_card_id=?", (card_id,))
            connection.execute("UPDATE exploration_suggestions SET resolved_card_id=NULL WHERE resolved_card_id=?", (card_id,))
            connection.execute("DELETE FROM decision_candidates WHERE card_id=?", (card_id,))
            connection.execute("DELETE FROM interactions WHERE card_id=?", (card_id,))
            connection.execute("DELETE FROM cards WHERE id=?", (card_id,))

    def add_time_entry(self, card_id: str, minutes: int, note: str = "") -> dict[str, Any]:
        card = self.get_card(card_id)
        if not card: raise KeyError(f"没有找到卡片：{card_id}")
        if card.category not in {"book", "game"}: raise ValueError("只有书籍和游戏支持投入时间记录")
        if minutes <= 0: raise ValueError("投入分钟数必须大于 0")
        with self.connect() as connection:
            cursor = connection.execute("INSERT INTO activity_sessions(card_id,minutes,note,recorded_at) VALUES (?,?,?,?)", (card_id, minutes, note.strip(), iso_now()))
            entry_id = int(cursor.lastrowid)
        return next(item for item in self.list_time_entries(card_id) if item["id"] == entry_id)

    def list_time_entries(self, card_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM activity_sessions WHERE card_id=? ORDER BY recorded_at DESC,id DESC", (card_id,)).fetchall()
        return [dict(row) for row in rows]

    def total_time(self, card_id: str) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT COALESCE(SUM(minutes),0) total FROM activity_sessions WHERE card_id=?", (card_id,)).fetchone()
        return int(row["total"])

    def delete_time_entry(self, entry_id: int) -> None:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM activity_sessions WHERE id=?", (entry_id,))
            if not cursor.rowcount: raise KeyError(f"没有找到时间记录：{entry_id}")

    def log_enrichment(self, *, card_id: str | None, category: str, title: str, status: str, model: str | None, error: str | None, added_tags: list[str], added_moods: list[str], retried: bool) -> None:
        with self.connect() as connection:
            connection.execute("""INSERT INTO ai_enrichment_logs(card_id,category,title,status,model,error,added_tags_json,added_moods_json,retried,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (card_id, category, title, status, model, error, json_dumps(added_tags), json_dumps(added_moods), int(retried), iso_now()))

    def has_interaction_since(self, card_id: str, action: str, since_iso: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM interactions
                   WHERE card_id=? AND action=? AND created_at>=? LIMIT 1""",
                (card_id, action, since_iso),
            ).fetchone()
        return row is not None

    def has_interaction_on_date(self, card_id: str, action: str, date_text: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM interactions
                   WHERE card_id=? AND action=? AND substr(created_at,1,10)=? LIMIT 1""",
                (card_id, action, date_text),
            ).fetchone()
        return row is not None

    def add_interaction(
        self,
        card_id: str,
        action: str,
        *,
        session_id: int | None = None,
        rating: int | None = None,
        review: str | None = None,
        payload: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> int:
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO interactions (
                    card_id, action, created_at, decision_session_id, rating, review, payload_json
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    card_id,
                    action,
                    created_at or iso_now(),
                    session_id,
                    rating,
                    review,
                    json_dumps(payload or {}),
                ),
            )
            return int(cursor.lastrowid)

    def get_preference_weights(self) -> dict[tuple[str, str], float]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT key_type, key, weight FROM preference_weights"
            ).fetchall()
        return {(row["key_type"], row["key"]): row["weight"] for row in rows}

    def adjust_preference(self, key_type: str, key: str, delta: float) -> float:
        normalized = key.strip().casefold()
        if not normalized:
            return 0.0
        with self.connect() as connection:
            row = connection.execute(
                "SELECT weight FROM preference_weights WHERE key_type=? AND key=?",
                (key_type, normalized),
            ).fetchone()
            old = float(row["weight"]) if row else 0.0
            new = max(-5.0, min(5.0, old + delta))
            connection.execute(
                """INSERT INTO preference_weights(key_type,key,weight,updated_at)
                   VALUES (?,?,?,?)
                   ON CONFLICT(key_type,key) DO UPDATE SET
                     weight=excluded.weight, updated_at=excluded.updated_at""",
                (key_type, normalized, new, iso_now()),
            )
        return new

    def reset_preferences(self) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM preference_weights")

    def save_decision(
        self,
        context: DecisionContext,
        candidates: list[Candidate],
        *,
        normalized_context: dict[str, Any] | None = None,
        decision_scope: str = "shelf_only",
        fallback_reason: str | None = None,
        eligible_count: int | None = None,
        top_fit_score: float | None = None,
    ) -> int:
        now = (context.now or parse_iso(iso_now())).isoformat(timespec="seconds")
        # Only the primary choice is actually shown to the user. Keep the full
        # ranking in decision_candidates for debugging, but do not make hidden
        # candidates look like they were recommended.
        shown = candidates[:1]
        primary_id = shown[0].card.id if shown else None
        with self.connect() as connection:
            cursor = connection.execute(
                """INSERT INTO decision_sessions (
                    created_at, available_minutes, energy_level, categories_json,
                    preferences_json, moods_json, free_text, normalized_context_json,
                    primary_card_id, recommendation_json, decision_scope, fallback_reason,
                    eligible_count, top_fit_score
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    now,
                    context.available_minutes,
                    context.energy_level,
                    json_dumps(context.categories),
                    json_dumps(context.genre_preferences or context.preferences),
                    json_dumps(context.moods),
                    context.free_text,
                    json_dumps(normalized_context or {}),
                    primary_id,
                    json_dumps([candidate.snapshot() for candidate in shown]),
                    decision_scope,
                    fallback_reason,
                    len(candidates) if eligible_count is None else eligible_count,
                    (
                        candidates[0].fit_score
                        if top_fit_score is None and candidates
                        else top_fit_score
                    ),
                ),
            )
            session_id = int(cursor.lastrowid)
            for rank, candidate in enumerate(candidates, start=1):
                connection.execute(
                    """INSERT INTO decision_candidates (
                        session_id, card_id, rank, total_score, score_json,
                        adjustments_json, explanation
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        session_id,
                        candidate.card.id,
                        rank,
                        candidate.total_score,
                        json_dumps(candidate.scores),
                        json_dumps(candidate.adjustments),
                        candidate.explanation,
                    ),
                )
            if shown:
                placeholders = ",".join("?" for _ in shown)
                connection.execute(
                    f"UPDATE cards SET last_recommended_at=?, updated_at=? WHERE id IN ({placeholders})",
                    (now, now, *(candidate.card.id for candidate in shown)),
                )
        return session_id

    def list_history(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT s.*, c.title AS primary_title
                   FROM decision_sessions s
                   LEFT JOIN cards c ON c.id=s.primary_card_id
                   ORDER BY s.created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            session_ids = [row["id"] for row in rows]
            interaction_map: dict[int, list[dict[str, Any]]] = {
                session_id: [] for session_id in session_ids
            }
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                interaction_rows = connection.execute(
                    f"""SELECT i.*, c.title AS card_title
                        FROM interactions i
                        JOIN cards c ON c.id=i.card_id
                        WHERE i.decision_session_id IN ({placeholders})
                        ORDER BY i.created_at""",
                    session_ids,
                ).fetchall()
                for interaction in interaction_rows:
                    interaction_map[interaction["decision_session_id"]].append(
                        {
                            **dict(interaction),
                            "payload": json_loads(interaction["payload_json"], {}),
                        }
                    )
            exploration_map: dict[int, list[dict[str, Any]]] = {
                session_id: [] for session_id in session_ids
            }
            if session_ids:
                placeholders = ",".join("?" for _ in session_ids)
                exploration_rows = connection.execute(
                    f"""SELECT * FROM exploration_suggestions
                        WHERE session_id IN ({placeholders}) ORDER BY created_at""",
                    session_ids,
                ).fetchall()
                for suggestion in exploration_rows:
                    exploration_map[suggestion["session_id"]].append(
                        self._row_to_exploration_dict(suggestion)
                    )
        return [
            {
                **dict(row),
                "categories": json_loads(row["categories_json"], []),
                "preferences": json_loads(row["preferences_json"], []),
                "moods": json_loads(row["moods_json"], []),
                "recommendations": json_loads(row["recommendation_json"], []),
                "interactions": interaction_map.get(row["id"], []),
                "exploration_suggestions": exploration_map.get(row["id"], []),
                "time_entries": self.list_time_entries(row["primary_card_id"]) if row["primary_card_id"] else [],
                "total_minutes": self.total_time(row["primary_card_id"]) if row["primary_card_id"] else 0,
            }
            for row in rows
        ]

    def get_cache(self, provider: str, cache_key: str) -> dict[str, Any] | None:
        now = iso_now()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT payload_json FROM metadata_cache
                   WHERE provider=? AND cache_key=? AND expires_at>=?""",
                (provider, cache_key, now),
            ).fetchone()
        return json_loads(row["payload_json"], None) if row else None

    def set_cache(
        self,
        provider: str,
        cache_key: str,
        payload: dict[str, Any],
        *,
        expires_at: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO metadata_cache(
                    provider, cache_key, payload_json, fetched_at, expires_at
                ) VALUES (?,?,?,?,?)
                ON CONFLICT(provider,cache_key) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    fetched_at=excluded.fetched_at,
                    expires_at=excluded.expires_at""",
                (provider, cache_key, json_dumps(payload), iso_now(), expires_at),
            )

    def add_exploration_suggestions(
        self, suggestions: list[ExplorationSuggestion]
    ) -> None:
        if not suggestions:
            return
        timestamp = iso_now()
        with self.connect() as connection:
            for suggestion in suggestions:
                connection.execute(
                    """INSERT INTO exploration_suggestions(
                        id, session_id, category, title, source, external_id,
                        draft_json, verified, fit_score, reason, is_best, resolution,
                        resolved_card_id, created_at, resolved_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
                    (
                        suggestion.id,
                        suggestion.session_id,
                        suggestion.draft.category,
                        suggestion.draft.title,
                        suggestion.draft.source,
                        suggestion.draft.external_id,
                        json_dumps(asdict(suggestion.draft)),
                        int(suggestion.verified),
                        suggestion.fit_score,
                        suggestion.reason,
                        int(suggestion.is_best),
                        suggestion.resolution,
                        suggestion.resolved_card_id,
                        timestamp,
                    ),
                )

    def get_exploration_suggestion(
        self, suggestion_id: str
    ) -> ExplorationSuggestion | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM exploration_suggestions WHERE id=?", (suggestion_id,)
            ).fetchone()
        return self._row_to_exploration(row) if row else None

    def resolve_exploration(
        self,
        suggestion_id: str,
        resolution: str,
        *,
        card_id: str | None = None,
    ) -> None:
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE exploration_suggestions SET
                    resolution=?, resolved_card_id=?, resolved_at=? WHERE id=?""",
                (resolution, card_id, iso_now(), suggestion_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"没有找到探索建议：{suggestion_id}")

    def recent_exploration_identities(self, since_iso: str) -> set[tuple[str, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT source, external_id, title FROM exploration_suggestions
                   WHERE created_at>=? AND resolution='dismissed'""",
                (since_iso,),
            ).fetchall()
        return {
            (row["source"], row["external_id"] or row["title"].casefold())
            for row in rows
        }

    @staticmethod
    def _row_to_exploration(row: sqlite3.Row) -> ExplorationSuggestion:
        draft_data = json_loads(row["draft_json"], {})
        return ExplorationSuggestion(
            id=row["id"],
            session_id=row["session_id"],
            draft=CardDraft(**draft_data),
            verified=bool(row["verified"]),
            fit_score=row["fit_score"],
            reason=row["reason"],
            resolution=row["resolution"],
            resolved_card_id=row["resolved_card_id"],
            is_best=bool(row["is_best"]) if "is_best" in row.keys() else False,
        )

    @classmethod
    def _row_to_exploration_dict(cls, row: sqlite3.Row) -> dict[str, Any]:
        result = cls._row_to_exploration(row).snapshot()
        result["created_at"] = row["created_at"]
        result["resolved_at"] = row["resolved_at"]
        return result

    @staticmethod
    def _card_values(card: Card) -> tuple[Any, ...]:
        return (
            card.id,
            card.category,
            card.title,
            title_key(card.title),
            card.status,
            card.duration_minutes,
            card.min_session_minutes,
            json_dumps(card.tags),
            card.energy_level,
            json_dumps(card.mood_fit),
            card.source,
            card.external_id,
            card.description,
            card.image_url,
            card.theme_color,
            card.theme_color_source,
            card.notes,
            card.priority,
            int(card.is_prioritized),
            json_dumps(card.extension),
            card.created_at,
            card.updated_at,
            card.last_recommended_at,
            card.completed_at,
            card.rating,
            card.review,
        )

    @staticmethod
    def _row_to_card(row: sqlite3.Row) -> Card:
        return Card(
            id=row["id"],
            category=row["category"],
            title=row["title"],
            status=row["status"],
            duration_minutes=row["duration_minutes"],
            min_session_minutes=row["min_session_minutes"],
            tags=json_loads(row["tags_json"], []),
            energy_level=row["energy_level"],
            mood_fit=json_loads(row["mood_fit_json"], []),
            source=row["source"],
            external_id=row["external_id"],
            description=row["description"],
            image_url=row["image_url"],
            theme_color=row["theme_color"] if "theme_color" in row.keys() else None,
            theme_color_source=row["theme_color_source"] if "theme_color_source" in row.keys() else "pending",
            notes=row["notes"],
            priority=row["priority"],
            is_prioritized=bool(row["is_prioritized"]),
            extension=json_loads(row["extension_json"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_recommended_at=row["last_recommended_at"],
            completed_at=row["completed_at"],
            rating=row["rating"],
            review=row["review"],
        )
