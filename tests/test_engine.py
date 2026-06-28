from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from decision_shelf.database import Database
from decision_shelf.engine import DecisionEngine, FeedbackService
from decision_shelf.models import Card, DecisionContext


FIXED_NOW = datetime(2026, 6, 27, 20, 0, tzinfo=timezone(timedelta(hours=8)))


class EngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "test.db")
        self.db.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add(self, card: Card) -> None:
        card.created_at = card.created_at or (FIXED_NOW - timedelta(days=90)).isoformat()
        self.db.add_card(card)

    def context(self, **overrides) -> DecisionContext:
        values = {
            "available_minutes": 60,
            "energy_level": "medium",
            "categories": ["movie", "book", "album", "game"],
            "preferences": [],
            "moods": [],
            "seed": "test-seed",
            "now": FIXED_NOW,
        }
        values.update(overrides)
        return DecisionContext(**values)

    def test_atomic_content_uses_full_duration_but_book_can_be_segmented(self) -> None:
        self.add(Card(id="movie", category="movie", title="长电影", duration_minutes=120))
        self.add(
            Card(
                id="book",
                category="book",
                title="长书",
                duration_minutes=1200,
                min_session_minutes=20,
            )
        )
        self.add(
            Card(
                id="game",
                category="game",
                title="需要长局的游戏",
                duration_minutes=1200,
                min_session_minutes=90,
            )
        )
        result = DecisionEngine(self.db).decide(
            self.context(available_minutes=30), persist=False
        )
        self.assertEqual([candidate.card.id for candidate in result.candidates], ["book"])

    def test_completed_removed_and_not_today_are_filtered(self) -> None:
        for card_id, status in (
            ("todo", "todo"),
            ("done", "completed"),
            ("gone", "removed"),
            ("later", "todo"),
        ):
            self.add(
                Card(
                    id=card_id,
                    category="album",
                    title=card_id,
                    duration_minutes=40,
                    status=status,
                )
            )
        self.db.add_interaction(
            "later", "not-today", created_at=FIXED_NOW.isoformat(timespec="seconds")
        )
        result = DecisionEngine(self.db).decide(self.context(), persist=False)
        self.assertEqual([candidate.card.id for candidate in result.candidates], ["todo"])

    def test_scores_are_reproducible_for_same_seed(self) -> None:
        self.add(Card(id="a", category="album", title="A", duration_minutes=45))
        first = DecisionEngine(self.db).decide(self.context(), persist=False)
        second = DecisionEngine(self.db).decide(self.context(), persist=False)
        self.assertEqual(first.candidates[0].total_score, second.candidates[0].total_score)
        self.assertEqual(first.candidates[0].scores, second.candidates[0].scores)

    def test_recent_recommendation_and_skip_apply_penalties(self) -> None:
        self.add(Card(id="a", category="album", title="A", duration_minutes=45))
        engine = DecisionEngine(self.db)
        initial = engine.decide(self.context(), persist=True)
        self.assertIsNotNone(initial.session_id)
        after_recommendation = engine.decide(self.context(), persist=False)
        self.assertEqual(
            after_recommendation.candidates[0].adjustments["recommended_recently"], -20.0
        )
        self.db.add_interaction(
            "a", "skip", created_at=FIXED_NOW.isoformat(timespec="seconds")
        )
        after_skip = engine.decide(self.context(), persist=False)
        self.assertEqual(after_skip.candidates[0].adjustments["skipped_this_week"], -15.0)

    def test_priority_and_feedback_change_preferences(self) -> None:
        self.add(
            Card(
                id="book",
                category="book",
                title="一本书",
                duration_minutes=400,
                min_session_minutes=20,
                tags=["认知"],
                mood_fit=["拓宽认知"],
            )
        )
        feedback = FeedbackService(self.db)
        prioritized = feedback.apply("book", "prioritize")
        self.assertTrue(prioritized.is_prioritized)
        scored = DecisionEngine(self.db).decide(self.context(), persist=False)
        self.assertEqual(scored.candidates[0].adjustments["prioritized"], 15.0)

        completed = feedback.apply("book", "complete", rating=5, review="很喜欢")
        self.assertEqual(completed.status, "completed")
        self.assertFalse(completed.is_prioritized)
        weights = self.db.get_preference_weights()
        self.assertGreater(weights[("category", "book")], 0)
        self.assertGreater(weights[("tag", "认知")], 0)
        result = DecisionEngine(self.db).decide(self.context(), persist=False)
        self.assertEqual(result.candidates, [])

    def test_preference_weights_are_clamped_and_resettable(self) -> None:
        for _ in range(20):
            self.db.adjust_preference("tag", "科幻", 1.0)
        self.assertEqual(self.db.get_preference_weights()[("tag", "科幻")], 5.0)
        self.db.reset_preferences()
        self.assertEqual(self.db.get_preference_weights(), {})

    def test_history_includes_result_rating_and_review(self) -> None:
        self.add(Card(id="album", category="album", title="专辑", duration_minutes=45))
        result = DecisionEngine(self.db).decide(self.context(), persist=True)
        FeedbackService(self.db).apply(
            "album",
            "complete",
            session_id=result.session_id,
            rating=5,
            review="正适合今晚",
        )
        history = self.db.list_history(limit=1)
        self.assertEqual(history[0]["primary_title"], "专辑")
        self.assertEqual(history[0]["interactions"][0]["action"], "complete")
        self.assertEqual(history[0]["interactions"][0]["rating"], 5)
        self.assertEqual(history[0]["interactions"][0]["review"], "正适合今晚")

    def test_only_primary_candidate_is_recorded_as_recommended(self) -> None:
        self.add(Card(id="a", category="album", title="A", duration_minutes=40))
        self.add(Card(id="b", category="album", title="B", duration_minutes=40))
        result = DecisionEngine(self.db).decide(self.context(), persist=True)
        history = self.db.list_history(limit=1)
        self.assertEqual(len(history[0]["recommendations"]), 1)
        primary_id = result.candidates[0].card.id
        secondary_id = result.candidates[1].card.id
        self.assertIsNotNone(self.db.get_card(primary_id).last_recommended_at)
        self.assertIsNone(self.db.get_card(secondary_id).last_recommended_at)

    def test_synonyms_and_or_matching_raise_fit(self) -> None:
        self.add(Card(id="fit", category="movie", title="适配", duration_minutes=55, tags=["科幻"], mood_fit=["灵感"], energy_level="medium"))
        result = DecisionEngine(self.db).decide(self.context(categories=["movie"], genre_preferences=["science fiction", "爱情"], moods=["获得灵感", "挑战"]), persist=False)
        self.assertGreaterEqual(result.candidates[0].fit_score, 80)
        self.assertEqual(result.candidates[0].match_details["matched_genres"], ["科幻"])

    def test_unselected_dimensions_are_removed_from_denominator(self) -> None:
        self.add(Card(id="plain", category="movie", title="普通", duration_minutes=60, tags=[], mood_fit=[]))
        score = DecisionEngine(self.db).decide(self.context(categories=["movie"]), persist=False).candidates[0]
        self.assertEqual(score.fit_score, 100.0)


if __name__ == "__main__":
    unittest.main()
