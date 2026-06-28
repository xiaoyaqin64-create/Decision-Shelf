from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, validator

from .models import CATEGORIES, DECISION_SCOPES, ENERGY_LEVELS, STATUSES


class CardDraftSchema(BaseModel):
    category: str
    title: str
    source: str = "manual"
    external_id: str | None = None
    description: str = ""
    image_url: str | None = None
    duration_minutes: int | None = None
    min_session_minutes: int | None = None
    tags: list[str] = Field(default_factory=list)
    energy_level: str = "medium"
    mood_fit: list[str] = Field(default_factory=list)
    notes: str = ""
    priority: int = 3
    extension: dict[str, Any] = Field(default_factory=dict)

    @validator("category")
    def valid_category(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError("不支持的分类")
        return value

    @validator("energy_level")
    def valid_energy(cls, value: str) -> str:
        if value not in ENERGY_LEVELS:
            raise ValueError("不支持的精力等级")
        return value

    @validator("title")
    def title_required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("标题不能为空")
        return value.strip()

    @validator("duration_minutes", "min_session_minutes")
    def positive_duration(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("时长必须大于 0")
        return value

    @validator("priority")
    def valid_priority(cls, value: int) -> int:
        if not 1 <= value <= 5:
            raise ValueError("优先级必须在 1～5 之间")
        return value


class CardCreate(CardDraftSchema):
    status: str = "todo"

    @validator("status")
    def valid_status(cls, value: str) -> str:
        if value not in STATUSES:
            raise ValueError("不支持的卡片状态")
        return value


class CardUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    status: str | None = None
    duration_minutes: int | None = None
    min_session_minutes: int | None = None
    tags: list[str] | None = None
    energy_level: str | None = None
    mood_fit: list[str] | None = None
    source: str | None = None
    external_id: str | None = None
    description: str | None = None
    image_url: str | None = None
    notes: str | None = None
    priority: int | None = None
    is_prioritized: bool | None = None
    extension: dict[str, Any] | None = None


class ActionRequest(BaseModel):
    action: Literal["start", "complete", "skip", "not-today", "prioritize", "remove"]
    session_id: int | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    review: str | None = None
    final_minutes: int | None = Field(default=None, gt=0)
    time_note: str = ""


class DecisionRequest(BaseModel):
    available_minutes: int = Field(gt=0)
    energy_level: str
    categories: list[str]
    preferences: list[str] = Field(default_factory=list)
    genre_preferences: list[str] = Field(default_factory=list)
    moods: list[str] = Field(default_factory=list)
    free_text: str = ""
    scope: str = "shelf_only"
    seed: str = "web"

    @validator("energy_level")
    def valid_energy(cls, value: str) -> str:
        if value not in ENERGY_LEVELS:
            raise ValueError("不支持的精力等级")
        return value

    @validator("categories")
    def valid_categories(cls, value: list[str]) -> list[str]:
        if not value or set(value) - set(CATEGORIES):
            raise ValueError("至少选择一个有效分类")
        return value

    @validator("scope")
    def valid_scope(cls, value: str) -> str:
        if value not in DECISION_SCOPES:
            raise ValueError("不支持的推荐范围")
        return value


class EnrichRequest(BaseModel):
    draft: CardDraftSchema


class ExplorationResolveRequest(BaseModel):
    action: Literal["add", "start", "complete", "dismiss"]
    draft: CardDraftSchema | None = None
    confirmed: bool = False


class TimeEntryRequest(BaseModel):
    minutes: int = Field(gt=0)
    note: str = ""


class ThemeColorResolveRequest(BaseModel):
    card_ids: list[str] = Field(min_items=1, max_items=20)


class CardImportPreviewRequest(BaseModel):
    filename: str
    content: str = Field(max_length=262144)


class CardImportItem(BaseModel):
    row_number: int = Field(ge=2)
    draft: CardDraftSchema


class CardImportRequest(BaseModel):
    items: list[CardImportItem] = Field(min_items=1, max_items=50)
