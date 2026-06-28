from __future__ import annotations

import hashlib
from datetime import datetime, timedelta

from .database import Database
from .models import Candidate, Card, DecisionContext, DecisionResult
from .taxonomy import canonicalize
from .utils import now_local, parse_iso


ENERGY_VALUE = {"low": 1, "medium": 2, "high": 3}


def _stable_tie(seed: str, card_id: str) -> str:
    return hashlib.sha256(f"{seed}:{card_id}".encode()).hexdigest()


def _or_match(desired: list[str], actual: list[str], maximum: float, *, unknown: float = .45) -> float:
    if not desired:
        return maximum
    if not actual:
        return maximum * unknown
    wanted = {item.casefold() for item in canonicalize(desired)}
    present = {item.casefold() for item in canonicalize(actual)}
    hits = len(wanted & present)
    if not hits:
        return 0.0
    # 任意命中先拿 80%，额外命中再逐步补足；不要求卡片同时满足全部愿望。
    return maximum * min(1.0, .8 + .2 * hits / max(1, len(wanted)))


class DecisionEngine:
    def __init__(self, database: Database):
        self.database = database

    def decide(self, context: DecisionContext, *, persist: bool = True, normalized_context: dict | None = None) -> DecisionResult:
        context.validate()
        current = context.now or now_local()
        weights = self.database.get_preference_weights()
        candidates = [self._score(card, context, current, weights) for card in self.database.list_cards() if self._eligible(card, context, current)]
        candidates.sort(key=lambda item: (-item.total_score, -item.fit_score, _stable_tie(context.seed, item.card.id)))
        result = DecisionResult(session_id=None, context=context, candidates=candidates)
        if persist:
            result.session_id = self.database.save_decision(context, candidates, normalized_context=normalized_context)
        return result

    def score_transient(self, card: Card, context: DecisionContext) -> Candidate:
        context.validate()
        return self._score(card, context, context.now or now_local(), self.database.get_preference_weights())

    def _eligible(self, card: Card, context: DecisionContext, current: datetime) -> bool:
        if card.status in {"completed", "removed"} or card.category not in context.categories:
            return False
        if card.required_minutes is not None and card.required_minutes > context.available_minutes:
            return False
        return not self.database.has_interaction_on_date(card.id, "not-today", current.date().isoformat())

    def _score(self, card: Card, context: DecisionContext, current: datetime, weights: dict[tuple[str, str], float]) -> Candidate:
        required = card.required_minutes
        if required is None:
            time_score = 18.0  # 资料未知：低置信中性分，不直接归零。
        else:
            ratio = min(1.0, required / context.available_minutes)
            time_score = 18.0 + 12.0 * ratio if card.category in {"movie", "album"} else 22.0 + 8.0 * min(1.0, context.available_minutes / max(required, 1))

        distance = abs(ENERGY_VALUE.get(card.energy_level, 2) - ENERGY_VALUE[context.energy_level])
        energy_score = {0: 20.0, 1: 12.0, 2: 5.0}[distance]
        genres = context.genre_preferences or context.preferences
        genre_active = bool(genres)
        scene_active = bool(context.moods)
        genre_score = _or_match(genres, card.tags, 25.0) if genre_active else 0.0
        scene_score = _or_match(context.moods, card.mood_fit, 25.0) if scene_active else 0.0

        scores = {"time": round(time_score, 2), "energy": energy_score}
        denominator = 50.0
        if genre_active:
            scores["genres"] = round(genre_score, 2); denominator += 25.0
        if scene_active:
            scores["scenes"] = round(scene_score, 2); denominator += 25.0
        fit_score = round(sum(scores.values()) / denominator * 100.0, 2)

        adjustments: dict[str, float] = {}
        last = parse_iso(card.last_recommended_at)
        if last:
            elapsed = current - last
            if elapsed < timedelta(hours=24): adjustments["recommended_recently"] = -20.0
            elif elapsed < timedelta(days=7): adjustments["recommended_this_week"] = -8.0
        if self.database.has_interaction_since(card.id, "skip", (current - timedelta(days=7)).isoformat(timespec="seconds")):
            adjustments["skipped_this_week"] = -15.0
        if card.is_prioritized: adjustments["prioritized"] = 15.0
        preference = weights.get(("category", card.category), 0.0)
        preference += sum(weights.get(("tag", tag.casefold()), 0.0) for tag in card.tags)
        preference += sum(weights.get(("mood", mood.casefold()), 0.0) for mood in card.mood_fit)
        preference = max(-8.0, min(8.0, preference))
        if preference: adjustments["long_term_preference"] = round(preference, 2)
        priority = (card.priority - 3) * 1.5
        if priority: adjustments["priority"] = priority
        total = max(0.0, min(115.0, fit_score + sum(adjustments.values())))
        normalized_genres = canonicalize(genres)
        normalized_scenes = canonicalize(context.moods)
        card_genres = canonicalize(card.tags)
        card_scenes = canonicalize(card.mood_fit)
        details = {
            "requested_genres": normalized_genres,
            "matched_genres": [x for x in normalized_genres if x.casefold() in {y.casefold() for y in card_genres}],
            "requested_scenes": normalized_scenes,
            "matched_scenes": [x for x in normalized_scenes if x.casefold() in {y.casefold() for y in card_scenes}],
        }
        return Candidate(card=card, total_score=round(total, 2), fit_score=fit_score, scores=scores, adjustments=adjustments, match_details=details)


class FeedbackService:
    def __init__(self, database: Database): self.database = database

    def apply(self, card_id: str, action: str, *, session_id: int | None = None, rating: int | None = None, review: str | None = None) -> Card:
        card = self.database.get_card(card_id)
        if card is None: raise KeyError(f"没有找到卡片：{card_id}")
        if action not in {"start", "complete", "skip", "not-today", "prioritize", "remove"}: raise ValueError(f"不支持的操作：{action}")
        if rating is not None and not 1 <= rating <= 5: raise ValueError("评分必须在 1～5 之间")
        timestamp = now_local().isoformat(timespec="seconds")
        if action == "start":
            card.status = "in_progress"; self._learn(card, .1, .05, .05)
        elif action == "complete":
            card.status = "completed"; card.completed_at = timestamp; card.rating = rating; card.review = review; card.is_prioritized = False
            multiplier = 1.75 if rating and rating >= 4 else (-.75 if rating and rating <= 2 else 1.0)
            self._learn(card, .4 * multiplier, .25 * multiplier, .2 * multiplier)
        elif action == "prioritize": card.is_prioritized = True
        elif action == "remove": card.status = "removed"
        self.database.update_card(card)
        self.database.add_interaction(card_id, action, session_id=session_id, rating=rating, review=review, created_at=timestamp)
        return card

    def _learn(self, card: Card, category_delta: float, tag_delta: float, mood_delta: float) -> None:
        self.database.adjust_preference("category", card.category, category_delta)
        for tag in card.tags: self.database.adjust_preference("tag", tag, tag_delta)
        for mood in card.mood_fit: self.database.adjust_preference("mood", mood, mood_delta)
