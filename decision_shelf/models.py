from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


CATEGORIES = ("movie", "book", "album", "game")
CATEGORY_LABELS = {
    "movie": "电影",
    "book": "书籍",
    "album": "专辑",
    "game": "游戏",
}
CATEGORY_ALIASES = {
    **{key: key for key in CATEGORIES},
    **{label: key for key, label in CATEGORY_LABELS.items()},
}
ENERGY_LEVELS = ("low", "medium", "high")
ENERGY_LABELS = {"low": "低", "medium": "中等", "high": "高"}
STATUSES = ("todo", "in_progress", "completed", "removed")
ACTIONS = ("start", "complete", "skip", "not-today", "prioritize", "remove")
DECISION_SCOPES = ("shelf_only", "shelf_first", "free")


@dataclass(slots=True)
class Card:
    id: str
    category: str
    title: str
    status: str = "todo"
    duration_minutes: int | None = None
    min_session_minutes: int | None = None
    tags: list[str] = field(default_factory=list)
    energy_level: str = "medium"
    mood_fit: list[str] = field(default_factory=list)
    source: str = "manual"
    external_id: str | None = None
    description: str = ""
    image_url: str | None = None
    theme_color: str | None = None
    theme_color_source: str = "pending"
    notes: str = ""
    priority: int = 3
    is_prioritized: bool = False
    extension: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    last_recommended_at: str | None = None
    completed_at: str | None = None
    rating: int | None = None
    review: str | None = None

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category)

    @property
    def required_minutes(self) -> int | None:
        if self.category in {"movie", "album"}:
            return self.duration_minutes
        return self.min_session_minutes or self.duration_minutes

    def validate(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"不支持的分类：{self.category}")
        if self.status not in STATUSES:
            raise ValueError(f"不支持的状态：{self.status}")
        if self.energy_level not in ENERGY_LEVELS:
            raise ValueError(f"不支持的精力等级：{self.energy_level}")
        if not self.title.strip():
            raise ValueError("标题不能为空")
        if self.theme_color_source not in {"pending", "extracted", "fallback"}:
            raise ValueError("不支持的主题色来源")
        if not 1 <= self.priority <= 5:
            raise ValueError("优先级必须在 1～5 之间")
        for value, name in (
            (self.duration_minutes, "总时长"),
            (self.min_session_minutes, "最小单次投入"),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name}必须大于 0")


@dataclass(slots=True)
class DecisionContext:
    available_minutes: int
    energy_level: str
    categories: list[str]
    preferences: list[str] = field(default_factory=list)
    genre_preferences: list[str] = field(default_factory=list)
    moods: list[str] = field(default_factory=list)
    free_text: str = ""
    seed: str = "default"
    now: datetime | None = None

    def validate(self) -> None:
        if self.available_minutes <= 0:
            raise ValueError("可用时间必须大于 0")
        if self.energy_level not in ENERGY_LEVELS:
            raise ValueError(f"不支持的精力等级：{self.energy_level}")
        invalid = set(self.categories) - set(CATEGORIES)
        if invalid:
            raise ValueError(f"不支持的分类：{', '.join(sorted(invalid))}")
        if not self.categories:
            raise ValueError("至少选择一个分类")


@dataclass(slots=True)
class Candidate:
    card: Card
    total_score: float
    fit_score: float
    scores: dict[str, float]
    adjustments: dict[str, float] = field(default_factory=dict)
    explanation: str = ""
    match_details: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {
            "card_id": self.card.id,
            "title": self.card.title,
            "category": self.card.category,
            "total_score": self.total_score,
            "fit_score": self.fit_score,
            "scores": self.scores,
            "adjustments": self.adjustments,
            "explanation": self.explanation,
            "match_details": self.match_details,
        }


@dataclass(slots=True)
class DecisionResult:
    session_id: int | None
    context: DecisionContext
    candidates: list[Candidate]

    def snapshot(self) -> dict[str, Any]:
        context = asdict(self.context)
        if isinstance(context.get("now"), datetime):
            context["now"] = context["now"].isoformat()
        return {
            "session_id": self.session_id,
            "context": context,
            "candidates": [candidate.snapshot() for candidate in self.candidates],
        }


@dataclass(slots=True)
class MetadataCandidate:
    source: str
    external_id: str
    category: str
    title: str
    subtitle: str = ""
    year: int | None = None
    creators: list[str] = field(default_factory=list)
    image_url: str | None = None
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CardDraft:
    category: str
    title: str
    source: str = "manual"
    external_id: str | None = None
    description: str = ""
    image_url: str | None = None
    duration_minutes: int | None = None
    min_session_minutes: int | None = None
    tags: list[str] = field(default_factory=list)
    energy_level: str = "medium"
    mood_fit: list[str] = field(default_factory=list)
    notes: str = ""
    priority: int = 3
    extension: dict[str, Any] = field(default_factory=dict)

    def to_card(self, card_id: str) -> Card:
        card = Card(
            id=card_id,
            category=self.category,
            title=self.title,
            source=self.source,
            external_id=self.external_id,
            description=self.description,
            image_url=self.image_url,
            duration_minutes=self.duration_minutes,
            min_session_minutes=self.min_session_minutes,
            tags=list(self.tags),
            energy_level=self.energy_level,
            mood_fit=list(self.mood_fit),
            notes=self.notes,
            priority=self.priority,
            extension=dict(self.extension),
        )
        card.validate()
        return card


@dataclass(slots=True)
class ExplorationSuggestion:
    id: str
    session_id: int
    draft: CardDraft
    verified: bool
    fit_score: float
    reason: str
    resolution: str = "pending"
    resolved_card_id: str | None = None
    is_best: bool = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "draft": asdict(self.draft),
            "verified": self.verified,
            "fit_score": self.fit_score,
            "reason": self.reason,
            "resolution": self.resolution,
            "resolved_card_id": self.resolved_card_id,
            "is_best": self.is_best,
        }
