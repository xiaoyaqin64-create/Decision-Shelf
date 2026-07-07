from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api_schemas import (
    ActionRequest,
    CardCreate,
    CardDraftSchema,
    CardImportPreviewRequest,
    CardImportRequest,
    CardUpdate,
    CompletionUpdate,
    DecisionRequest,
    EnrichRequest,
    ExplorationResolveRequest,
    TimeEntryRequest,
    ThemeColorResolveRequest,
    SettingsUpdate,
)
from .database import Database
from .csv_import import preview_csv_import
from .deepseek import AIService, DeepSeekConfig
from .engine import FeedbackService
from .metadata import MetadataError, MetadataService, ProviderRegistry
from .models import CardDraft, DecisionContext
from .utils import make_card_id, normalize_terms, now_local
from .taxonomy import GENRE_TAGS, SCENE_TAGS, canonicalize, taxonomy_payload
from .workflows import DecisionWorkflow
from .theme_color import ThemeColorService
from .backup import BackupError, BackupService, MAX_BACKUP_BYTES
from .app_paths import bundled_static_dir
from .settings import CredentialStoreError, public_settings, save_user_settings


def _draft_from_schema(schema: CardDraftSchema) -> CardDraft:
    return CardDraft(**schema.dict())


def _card_payload(card) -> dict[str, Any]:
    return asdict(card)


def _error(code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message, "retryable": retryable}


def create_app(
    database: Database | None = None,
    *,
    metadata: MetadataService | None = None,
    ai: AIService | None = None,
    workflow: DecisionWorkflow | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    db = database or Database()
    db.initialize()
    ai_service = ai or AIService()
    metadata_service = metadata or MetadataService(db, ProviderRegistry())
    decision_workflow = workflow or DecisionWorkflow(
        db, ai=ai_service, metadata=metadata_service
    )
    theme_colors = ThemeColorService(db)
    backups = BackupService(db)

    app = FastAPI(title="Decision Shelf API", version=__version__)
    app.state.database = db
    app.state.ai = ai_service
    app.state.metadata = metadata_service
    app.state.workflow = decision_workflow
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(MetadataError)
    async def metadata_error_handler(_request: Request, exc: MetadataError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_error(exc.code, exc.message, exc.retryable),
        )

    @app.exception_handler(KeyError)
    async def key_error_handler(_request: Request, exc: KeyError):
        return JSONResponse(
            status_code=404,
            content=_error("not_found", str(exc).strip("'")),
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_request: Request, exc: ValueError):
        return JSONResponse(status_code=422, content=_error("invalid_input", str(exc)))

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error_handler(_request: Request, _exc: sqlite3.IntegrityError):
        return JSONResponse(
            status_code=409,
            content=_error("duplicate_card", "该外部内容已经存在于书架中"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        return JSONResponse(
            status_code=422,
            content=_error("invalid_input", first.get("msg", "请求参数不正确")),
        )

    @app.exception_handler(CredentialStoreError)
    async def credential_store_error_handler(_request: Request, exc: CredentialStoreError):
        return JSONResponse(
            status_code=503,
            content=_error("credential_store_unavailable", str(exc), True),
        )

    @app.exception_handler(BackupError)
    async def backup_error_handler(_request: Request, exc: BackupError):
        return JSONResponse(
            status_code=422,
            content=_error("invalid_backup", str(exc), False),
        )

    @app.get("/api/config")
    def config():
        return {
            "version": __version__,
            "deepseek": {"available": ai_service.client.available},
            "metadata": metadata_service.status(),
        }

    @app.get("/api/settings")
    def settings():
        return public_settings()

    @app.put("/api/settings")
    def update_settings(payload: SettingsUpdate):
        values = {
            "DEEPSEEK_BASE_URL": payload.deepseek_base_url,
            "DEEPSEEK_MODEL": payload.deepseek_model,
            "MUSICBRAINZ_CONTACT": payload.musicbrainz_contact,
        }
        # Empty secret fields mean “keep the saved value”; explicit removal has
        # its own endpoint so opening the form can never erase a secret.
        if payload.deepseek_api_key:
            values["DEEPSEEK_API_KEY"] = payload.deepseek_api_key
        if payload.tmdb_read_access_token:
            values["TMDB_READ_ACCESS_TOKEN"] = payload.tmdb_read_access_token
        save_user_settings(values)
        ai_service.client.config = DeepSeekConfig.from_env()
        metadata_service.registry = ProviderRegistry()
        return public_settings()

    @app.delete("/api/settings/{secret}")
    def remove_secret(secret: str):
        mapping = {
            "deepseek": "DEEPSEEK_API_KEY",
            "tmdb": "TMDB_READ_ACCESS_TOKEN",
        }
        if secret not in mapping:
            raise ValueError("不支持的配置项")
        save_user_settings({mapping[secret]: ""})
        ai_service.client.config = DeepSeekConfig.from_env()
        metadata_service.registry = ProviderRegistry()
        return public_settings()

    @app.get("/api/backup/export")
    def export_backup():
        snapshot = backups.create_snapshot()
        filename = f"Decision-Shelf-{now_local().strftime('%Y%m%d-%H%M%S')}.dsbackup"
        def stream_snapshot():
            try:
                with snapshot.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        yield chunk
            finally:
                snapshot.unlink(missing_ok=True)

        return StreamingResponse(
            stream_snapshot(),
            media_type="application/x-sqlite3",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.post("/api/backup/restore")
    async def restore_backup(request: Request):
        content_length = int(request.headers.get("content-length", "0") or 0)
        if content_length > MAX_BACKUP_BYTES:
            raise BackupError("备份文件不能超过 128 MB")
        descriptor, raw_path = tempfile.mkstemp(
            prefix="decision-shelf-upload-", suffix=".dsbackup", dir=db.path.parent
        )
        os.close(descriptor)
        uploaded = Path(raw_path)
        size = 0
        try:
            with uploaded.open("wb") as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_BACKUP_BYTES:
                        raise BackupError("备份文件不能超过 128 MB")
                    output.write(chunk)
            if not size:
                raise BackupError("请选择备份文件")
            result = backups.restore(uploaded)
            return {"ok": True, **result}
        finally:
            uploaded.unlink(missing_ok=True)

    @app.get("/api/taxonomy")
    def taxonomy():
        return taxonomy_payload()

    @app.get("/api/cards")
    def cards(
        category: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ):
        return {
            "items": [
                _card_payload(card)
                for card in db.list_cards(category=category, status=status, query=q)
            ]
        }

    @app.post("/api/cards", status_code=201)
    def create_card(payload: CardCreate):
        draft_data = payload.dict(exclude={"status"})
        draft = CardDraft(**draft_data)
        card = draft.to_card(make_card_id(draft.category, draft.title))
        card.status = payload.status
        if card.status == "completed" and not card.completed_at:
            card.completed_at = now_local().isoformat(timespec="seconds")
        card, outcome = db.upsert_card(card)
        return {**_card_payload(card), "upsert_result": outcome}

    @app.post("/api/cards/import/preview")
    def preview_card_import(payload: CardImportPreviewRequest):
        if not payload.filename.casefold().endswith(".csv"):
            raise ValueError("请选择 .csv 文件")
        return preview_csv_import(payload.content, db)

    @app.post("/api/cards/import")
    def import_cards(payload: CardImportRequest):
        results = []
        for item in payload.items:
            draft = _draft_from_schema(item.draft)
            existing = (
                db.find_by_external(draft.source, draft.external_id)
                if draft.external_id
                else None
            ) or db.find_by_title(draft.category, draft.title)
            if existing:
                results.append({
                    "row_number": item.row_number,
                    "status": "skipped_duplicate",
                    "card": _card_payload(existing),
                    "message": "书架中已存在该卡片",
                })
                continue
            try:
                card = draft.to_card(make_card_id(draft.category, draft.title))
                db.add_card(card)
                results.append({
                    "row_number": item.row_number,
                    "status": "created",
                    "card": _card_payload(card),
                    "message": "",
                })
            except sqlite3.IntegrityError:
                results.append({
                    "row_number": item.row_number,
                    "status": "skipped_duplicate",
                    "card": None,
                    "message": "导入时发现重复卡片",
                })
            except ValueError as exc:
                results.append({
                    "row_number": item.row_number,
                    "status": "failed",
                    "card": None,
                    "message": str(exc),
                })
        return {
            "items": results,
            "summary": {
                "created": sum(item["status"] == "created" for item in results),
                "skipped": sum(item["status"] == "skipped_duplicate" for item in results),
                "failed": sum(item["status"] == "failed" for item in results),
            },
        }

    @app.post("/api/cards/theme-colors/resolve")
    def resolve_theme_colors(payload: ThemeColorResolveRequest):
        cards_to_resolve = []
        for card_id in dict.fromkeys(payload.card_ids):
            card = db.get_card(card_id)
            if card is None:
                raise KeyError(f"没有找到卡片：{card_id}")
            cards_to_resolve.append(card)
        return {"items": theme_colors.resolve_many(cards_to_resolve)}

    @app.get("/api/cards/{card_id}")
    def get_card(card_id: str):
        card = db.get_card(card_id)
        if card is None:
            raise KeyError(f"没有找到卡片：{card_id}")
        return _card_payload(card)

    @app.patch("/api/cards/{card_id}")
    def update_card(card_id: str, payload: CardUpdate):
        card = db.get_card(card_id)
        if card is None:
            raise KeyError(f"没有找到卡片：{card_id}")
        previous_status = card.status
        for field_name in payload.__fields_set__:
            value = getattr(payload, field_name)
            if value is not None:
                setattr(card, field_name, value)
        if previous_status != "completed" and card.status == "completed" and not card.completed_at:
            card.completed_at = now_local().isoformat(timespec="seconds")
            card.extension.pop("completed_at_inferred", None)
        db.update_card(card)
        return _card_payload(card)

    @app.patch("/api/cards/{card_id}/completion")
    def update_completion(card_id: str, payload: CompletionUpdate):
        card = db.get_card(card_id)
        if card is None:
            raise KeyError(f"没有找到卡片：{card_id}")
        if card.status != "completed":
            raise ValueError("只有已完成卡片可以修改完成记录")
        if "completed_at" in payload.__fields_set__:
            if payload.completed_at is None:
                raise ValueError("完成日期不能为空")
            card.completed_at = payload.completed_at.isoformat()
            card.extension.pop("completed_at_inferred", None)
        if "rating" in payload.__fields_set__:
            card.rating = payload.rating
        if "review" in payload.__fields_set__:
            card.review = payload.review.strip() if payload.review else None
        db.update_card(card)
        return _card_payload(card)

    @app.delete("/api/cards/{card_id}")
    def recycle_card(card_id: str):
        return _card_payload(FeedbackService(db).apply(card_id, "remove"))

    @app.post("/api/cards/{card_id}/restore")
    def restore_card(card_id: str):
        return _card_payload(db.restore_card(card_id))

    @app.delete("/api/cards/{card_id}/permanent")
    def permanent_delete_card(card_id: str):
        db.permanent_delete_card(card_id)
        return {"ok": True}

    @app.get("/api/cards/{card_id}/time-entries")
    def time_entries(card_id: str):
        if not db.get_card(card_id): raise KeyError(f"没有找到卡片：{card_id}")
        return {"items": db.list_time_entries(card_id), "total_minutes": db.total_time(card_id)}

    @app.post("/api/cards/{card_id}/time-entries", status_code=201)
    def add_time_entry(card_id: str, payload: TimeEntryRequest):
        item = db.add_time_entry(card_id, payload.minutes, payload.note)
        return {"item": item, "total_minutes": db.total_time(card_id)}

    @app.delete("/api/time-entries/{entry_id}")
    def delete_time_entry(entry_id: int):
        db.delete_time_entry(entry_id)
        return {"ok": True}

    @app.post("/api/cards/{card_id}/actions")
    def card_action(card_id: str, payload: ActionRequest):
        if payload.action == "complete" and payload.final_minutes:
            db.add_time_entry(card_id, payload.final_minutes, payload.time_note or "完成前最后一次投入")
        card = FeedbackService(db).apply(
            card_id,
            payload.action,
            session_id=payload.session_id,
            rating=payload.rating,
            review=payload.review,
            completed_at=payload.completed_at.isoformat() if payload.completed_at else None,
        )
        return _card_payload(card)

    @app.post("/api/decisions")
    def decide(payload: DecisionRequest):
        context = DecisionContext(
            available_minutes=payload.available_minutes,
            energy_level=payload.energy_level,
            categories=payload.categories,
            preferences=payload.preferences,
            genre_preferences=payload.genre_preferences,
            moods=payload.moods,
            free_text=payload.free_text,
            seed=payload.seed,
        )
        result = decision_workflow.decide(context, payload.scope)
        return {
            "session_id": result.session_id,
            "scope": result.scope,
            "shelf_recommendation": (
                result.shelf_recommendation.snapshot()
                if result.shelf_recommendation
                else None
            ),
            "exploration_suggestions": [
                suggestion.snapshot() for suggestion in result.exploration_suggestions
            ],
            "eligible_count": result.eligible_count,
            "top_fit_score": result.top_fit_score,
            "fallback_reason": result.fallback_reason,
            "exploration_error": result.exploration_error,
            "warnings": result.warnings,
        }

    @app.post("/api/exploration/{suggestion_id}/resolve")
    def resolve_exploration(
        suggestion_id: str, payload: ExplorationResolveRequest
    ):
        card = decision_workflow.resolve(
            suggestion_id,
            payload.action,
            edited_draft=_draft_from_schema(payload.draft) if payload.draft else None,
            confirmed=payload.confirmed,
        )
        return {"action": payload.action, "card": _card_payload(card) if card else None}

    @app.get("/api/history")
    def history(limit: int = Query(default=20, ge=1, le=100)):
        return {"items": db.list_history(limit)}

    @app.get("/api/preferences")
    def preferences():
        return {
            "items": [
                {"key_type": key_type, "key": key, "weight": weight}
                for (key_type, key), weight in sorted(db.get_preference_weights().items())
            ]
        }

    @app.delete("/api/preferences")
    def reset_preferences():
        db.reset_preferences()
        return {"ok": True}

    @app.get("/api/metadata/{category}/search")
    def metadata_search(category: str, q: str = Query(min_length=2)):
        return {
            "items": [asdict(item) for item in metadata_service.search(category, q)]
        }

    @app.get("/api/metadata/{category}/draft")
    def metadata_draft(category: str, source_id: str):
        return asdict(metadata_service.draft(category, source_id))

    @app.post("/api/metadata/enrich")
    def metadata_enrich(payload: EnrichRequest):
        return _enrich(_draft_from_schema(payload.draft), None)

    @app.post("/api/cards/{card_id}/enrich")
    def enrich_existing(card_id: str):
        card = db.get_card(card_id)
        if not card: raise KeyError(f"没有找到卡片：{card_id}")
        draft = CardDraft(**{name: getattr(card, name) for name in CardDraft.__dataclass_fields__})
        return _enrich(draft, card_id)

    def _enrich(draft: CardDraft, card_id: str | None):
        description_source = None
        if not draft.description.strip() and draft.external_id and draft.source in {"tmdb", "openlibrary", "musicbrainz"}:
            try:
                external = metadata_service.draft(draft.category, draft.external_id)
                if external.description.strip():
                    draft.description = external.description.strip()
                    description_source = f"external:{draft.source}"
                    draft.extension["description_provenance"] = {
                        "source": draft.source,
                        "mode": "external",
                        "generated_at": now_local().isoformat(timespec="seconds"),
                    }
            except MetadataError:
                # 外部简介不可用时继续进入明确标记的 AI 草稿流程。
                pass
        temp = draft.to_card(card_id or make_card_id(draft.category, draft.title))
        suggestion = ai_service.suggest_card_metadata(temp)
        old_tags, old_moods = set(draft.tags), set(draft.mood_fit)
        draft.tags = canonicalize([*draft.tags, *suggestion["tags"]], GENRE_TAGS[draft.category])
        draft.mood_fit = canonicalize([*draft.mood_fit, *suggestion["mood_fit"]], SCENE_TAGS)
        draft.energy_level = suggestion["energy_level"]
        if not draft.description.strip() and suggestion.get("description"):
            draft.description = suggestion["description"]
            description_source = f"deepseek:{suggestion['description_mode']}"
            draft.extension["description_provenance"] = {
                "source": "deepseek",
                "mode": suggestion["description_mode"],
                "basis": suggestion.get("description_basis", []),
                "model": ai_service.client.config.model,
                "generated_at": now_local().isoformat(timespec="seconds"),
            }
        added_tags = [item for item in draft.tags if item not in old_tags]
        added_moods = [item for item in draft.mood_fit if item not in old_moods]
        db.log_enrichment(card_id=card_id, category=draft.category, title=draft.title,
            status="success" if suggestion["source"] == "deepseek" else ("partial" if description_source else "error"),
            model=ai_service.client.config.model, error=ai_service.last_error,
            added_tags=added_tags, added_moods=added_moods, retried=bool(suggestion.get("retried")),
            description_added=bool(description_source), description_mode=description_source)
        return {"draft": asdict(draft), "source": suggestion["source"], "warning": ai_service.last_error, "retried": bool(suggestion.get("retried")), "description_source": description_source}

    resolved_static = Path(static_dir) if static_dir else bundled_static_dir()
    if resolved_static.exists():
        app.mount("/", StaticFiles(directory=resolved_static, html=True), name="frontend")
    else:
        @app.get("/")
        def root():
            return {
                "message": "Decision Shelf API 正在运行。开发界面请启动 frontend 的 Vite 服务。",
                "docs": "/docs",
            }

    return app


app = create_app()
