from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database


MAX_BACKUP_BYTES = 128 * 1024 * 1024
SUPPORTED_SCHEMA_VERSION = 5
REQUIRED_TABLES = {
    "schema_meta",
    "cards",
    "decision_sessions",
    "decision_candidates",
    "interactions",
    "preference_weights",
}


class BackupError(ValueError):
    pass


class BackupService:
    def __init__(self, database: Database):
        self.database = database

    def create_snapshot(self) -> Path:
        self.database.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(
            prefix="decision-shelf-export-", suffix=".dsbackup", dir=self.database.path.parent
        )
        os.close(descriptor)
        destination = Path(raw_path)
        try:
            with closing(sqlite3.connect(self.database.path)) as source, closing(
                sqlite3.connect(destination)
            ) as target:
                source.backup(target)
            self.validate(destination)
            return destination
        except Exception:
            destination.unlink(missing_ok=True)
            raise

    def validate(self, path: str | Path) -> dict[str, Any]:
        candidate = Path(path)
        if not candidate.exists() or candidate.stat().st_size < 100:
            raise BackupError("备份文件为空或不完整")
        if candidate.stat().st_size > MAX_BACKUP_BYTES:
            raise BackupError("备份文件不能超过 128 MB")
        with candidate.open("rb") as stream:
            header = stream.read(16)
        if header != b"SQLite format 3\x00":
            raise BackupError("这不是有效的 Decision Shelf 备份文件")
        try:
            connection = sqlite3.connect(candidate)
            connection.row_factory = sqlite3.Row
            check = connection.execute("PRAGMA quick_check").fetchone()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if not check or check[0] != "ok":
                raise BackupError("备份数据库完整性检查失败")
            if not REQUIRED_TABLES.issubset(tables):
                raise BackupError("备份缺少必要的数据表")
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key='version'"
            ).fetchone()
            version = int(row[0]) if row else 1
            if version > SUPPORTED_SCHEMA_VERSION:
                raise BackupError("该备份来自更新版本的 Decision Shelf，请先升级应用")
            counts = {
                "cards": connection.execute("SELECT COUNT(*) FROM cards").fetchone()[0],
                "history": connection.execute(
                    "SELECT COUNT(*) FROM decision_sessions"
                ).fetchone()[0],
            }
            return {"version": version, **counts}
        except BackupError:
            raise
        except (sqlite3.Error, ValueError, OSError) as exc:
            raise BackupError("无法读取备份数据库") from exc
        finally:
            if "connection" in locals():
                connection.close()

    def restore(self, uploaded_path: str | Path) -> dict[str, Any]:
        candidate_path = Path(uploaded_path)
        metadata = self.validate(candidate_path)

        # Migrate a working copy first. The live database is untouched unless
        # validation and migration both succeed.
        descriptor, migrated_raw = tempfile.mkstemp(
            prefix="decision-shelf-restore-", suffix=".db", dir=self.database.path.parent
        )
        os.close(descriptor)
        migrated = Path(migrated_raw)
        migrated.unlink(missing_ok=True)
        safety_backup = self.database.path.with_name(
            f"decision_shelf.pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S')}.bak"
        )
        try:
            with closing(sqlite3.connect(candidate_path)) as source, closing(
                sqlite3.connect(migrated)
            ) as target:
                source.backup(target)
            Database(migrated).initialize()
            metadata = self.validate(migrated)

            with closing(sqlite3.connect(self.database.path)) as live, closing(
                sqlite3.connect(safety_backup)
            ) as safety:
                live.backup(safety)
            try:
                with closing(sqlite3.connect(migrated)) as source, closing(
                    sqlite3.connect(self.database.path)
                ) as live:
                    source.backup(live)
                self.database.initialize()
            except Exception:
                with closing(sqlite3.connect(safety_backup)) as safety, closing(
                    sqlite3.connect(self.database.path)
                ) as live:
                    safety.backup(live)
                self.database.initialize()
                raise
            return {**metadata, "safety_backup": safety_backup.name}
        except BackupError:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise BackupError("恢复备份失败，原有数据已保留") from exc
        finally:
            migrated.unlink(missing_ok=True)
