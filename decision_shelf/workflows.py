from __future__ import annotations

import difflib
import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .database import Database
from .deepseek import AIService, DeepSeekError
from .engine import DecisionEngine, FeedbackService
from .metadata import MetadataError, MetadataService
from .models import (
    DECISION_SCOPES,
    Candidate,
    Card,
    CardDraft,
    DecisionContext,
    ExplorationSuggestion,
    MetadataCandidate,
)
from .utils import make_card_id, normalize_terms, now_local
from .taxonomy import GENRE_TAGS, SCENE_TAGS, canonicalize, title_key


@dataclass(slots=True)
class WorkflowResult:
    session_id: int
    scope: str
    shelf_recommendation: Candidate | None
    exploration_suggestions: list[ExplorationSuggestion]
    eligible_count: int
    top_fit_score: float | None
    fallback_reason: str | None = None
    exploration_error: str | None = None
    warnings: list[str] = field(default_factory=list)


class DecisionWorkflow:
    def __init__(
        self,
        database: Database,
        *,
        ai: AIService | None = None,
        metadata: MetadataService | None = None,
    ):
        self.database = database
        self.ai = ai or AIService()
        self.metadata = metadata or MetadataService(database)
        self.engine = DecisionEngine(database)

    def decide(self, context: DecisionContext, scope: str = "shelf_only") -> WorkflowResult:
        if scope not in DECISION_SCOPES:
            raise ValueError(f"不支持的推荐范围：{scope}")
        context.validate()
        normalized = self.ai.merge_context(context)
        shelf_result = self.engine.decide(context, persist=False)
        eligible_count = len(shelf_result.candidates)
        top_fit_score = (
            shelf_result.candidates[0].fit_score if shelf_result.candidates else None
        )
        fallback_reason: str | None = None
        explore = scope == "free"
        if scope == "shelf_first":
            if eligible_count <= 3:
                fallback_reason = "low_count"
                explore = True
            elif top_fit_score is not None and top_fit_score < 60:
                fallback_reason = "low_fit"
                explore = True

        shelf_candidates = [] if scope == "free" else shelf_result.candidates
        if shelf_candidates:
            self.ai.explain_candidates(shelf_candidates, context)
        session_id = self.database.save_decision(
            context,
            shelf_candidates,
            normalized_context=normalized,
            decision_scope=scope,
            fallback_reason=fallback_reason,
            eligible_count=eligible_count,
            top_fit_score=top_fit_score,
        )

        suggestions: list[ExplorationSuggestion] = []
        warnings: list[str] = []
        exploration_error: str | None = None
        if explore:
            try:
                suggestions, warnings = self._explore(context, session_id)
            except DeepSeekError as exc:
                exploration_error = str(exc)

        return WorkflowResult(
            session_id=session_id,
            scope=scope,
            shelf_recommendation=shelf_candidates[0] if shelf_candidates else None,
            exploration_suggestions=suggestions,
            eligible_count=eligible_count,
            top_fit_score=top_fit_score,
            fallback_reason=fallback_reason,
            exploration_error=exploration_error,
            warnings=warnings,
        )

    def _explore(
        self, context: DecisionContext, session_id: int
    ) -> tuple[list[ExplorationSuggestion], list[str]]:
        existing_cards = self.database.list_cards()
        excluded_titles = [card.title for card in existing_cards]
        existing_title_keys = {_title_key(card.title) for card in existing_cards}
        ignored = self.database.recent_exploration_identities(
            (now_local() - timedelta(days=30)).isoformat(timespec="seconds")
        )
        proposals = self.ai.generate_exploration_candidates(
            context, excluded_titles=excluded_titles, count=12
        )
        suggestions: list[ExplorationSuggestion] = []
        warnings: list[str] = []
        seen: set[tuple[str, str]] = set()

        for proposal in proposals:
            if _title_key(proposal["title"]) in existing_title_keys:
                continue
            try:
                draft, verified = self._proposal_to_draft(proposal)
            except MetadataError as exc:
                warnings.append(f"{proposal['title']}：{exc.message}")
                continue
            identity = (draft.source, draft.external_id or _title_key(draft.title))
            if identity in seen or identity in ignored:
                continue
            if draft.external_id and self.database.find_by_external(
                draft.source, draft.external_id
            ):
                continue
            if _title_key(draft.title) in existing_title_keys:
                continue

            draft.tags = canonicalize([*draft.tags, *proposal.get("tags", [])], GENRE_TAGS[draft.category])
            draft.mood_fit = canonicalize([*draft.mood_fit, *proposal.get("mood_fit", [])], SCENE_TAGS)
            draft.energy_level = proposal.get("energy_level", draft.energy_level)
            transient = draft.to_card(f"transient_{uuid.uuid4().hex[:8]}")
            required = transient.required_minutes
            if required is not None and required > context.available_minutes:
                continue
            scored = self.engine.score_transient(transient, context)
            suggestion = ExplorationSuggestion(
                id=f"exp_{uuid.uuid4().hex}",
                session_id=session_id,
                draft=draft,
                verified=verified,
                fit_score=scored.fit_score,
                reason=proposal.get("reason") or "它与当前状态和偏好较为匹配。",
            )
            suggestions.append(suggestion)
            seen.add(identity)

        suggestions.sort(key=lambda item: (-item.fit_score, item.draft.title))
        suggestions = suggestions[:3]
        if suggestions:
            suggestions[0].is_best = True
        self.database.add_exploration_suggestions(suggestions)
        return suggestions, warnings

    def _proposal_to_draft(
        self, proposal: dict[str, Any]
    ) -> tuple[CardDraft, bool]:
        category = proposal["category"]
        if category == "game":
            return (
                CardDraft(
                    category="game",
                    title=proposal["title"],
                    source="ai",
                    description=proposal.get("reason", ""),
                    duration_minutes=proposal.get("duration_minutes"),
                    min_session_minutes=proposal.get("min_session_minutes") or 30,
                    tags=list(proposal.get("tags", [])),
                    mood_fit=list(proposal.get("mood_fit", [])),
                    energy_level=proposal.get("energy_level", "medium"),
                    extension={"studio": proposal.get("creator", ""), "year": proposal.get("year")},
                ),
                False,
            )

        candidates = self.metadata.search(category, proposal["title"], limit=8)
        match = _best_match(candidates, proposal)
        if match is None:
            raise MetadataError("unverified", "没有找到足够可信的外部实体")
        draft = self.metadata.draft(category, match.external_id)
        return draft, True

    def resolve(
        self,
        suggestion_id: str,
        action: str,
        *,
        edited_draft: CardDraft | None = None,
        confirmed: bool = False,
    ) -> Card | None:
        suggestion = self.database.get_exploration_suggestion(suggestion_id)
        if suggestion is None:
            raise KeyError(f"没有找到探索建议：{suggestion_id}")
        if suggestion.resolution != "pending":
            raise ValueError("该探索建议已经处理过")
        if action == "dismiss":
            self.database.resolve_exploration(suggestion_id, "dismissed")
            return None
        if action not in {"add", "start", "complete"}:
            raise ValueError(f"不支持的探索操作：{action}")
        if not suggestion.verified and not confirmed:
            raise ValueError("未经外部验证的建议必须编辑并确认后才能保存")
        draft = edited_draft or suggestion.draft
        card, _ = self.database.upsert_card(draft.to_card(make_card_id(draft.category, draft.title)))
        if action == "start" and card.status != "in_progress":
            card = FeedbackService(self.database).apply(
                card.id, "start", session_id=suggestion.session_id
            )
        elif action == "complete" and card.status != "completed":
            card = FeedbackService(self.database).apply(card.id, "complete", session_id=suggestion.session_id)
        self.database.resolve_exploration(
            suggestion_id,
            "completed" if action == "complete" else ("started" if action == "start" else "added"),
            card_id=card.id,
        )
        return card


def _title_key(value: str) -> str:
    return title_key(value)


def _best_match(
    candidates: list[MetadataCandidate], proposal: dict[str, Any]
) -> MetadataCandidate | None:
    if not candidates:
        return None
    wanted_title = _title_key(proposal["title"])
    wanted_creator = str(proposal.get("creator", "")).casefold()
    wanted_year = proposal.get("year")
    scored: list[tuple[float, MetadataCandidate]] = []
    for candidate in candidates:
        ratio = difflib.SequenceMatcher(None, wanted_title, _title_key(candidate.title)).ratio()
        score = ratio
        if wanted_creator and any(
            wanted_creator in creator.casefold() or creator.casefold() in wanted_creator
            for creator in candidate.creators
        ):
            score += 0.2
        if wanted_year and candidate.year == wanted_year:
            score += 0.1
        scored.append((score, candidate))
    score, candidate = max(scored, key=lambda item: item[0])
    return candidate if score >= 0.55 else None
