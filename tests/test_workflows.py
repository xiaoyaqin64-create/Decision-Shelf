from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decision_shelf.database import Database
from decision_shelf.models import Card, CardDraft, DecisionContext, MetadataCandidate
from decision_shelf.workflows import DecisionWorkflow


class FakeClient:
    available = True


class FakeAI:
    def __init__(self): self.client = FakeClient(); self.last_error = None
    def merge_context(self, context): return {"source": "fake", "moods": [], "preferences": []}
    def explain_candidates(self, candidates, context):
        if candidates: candidates[0].explanation = "书架推荐理由"
        return candidates
    def generate_exploration_candidates(self, context, *, excluded_titles, count=6):
        return [
            {"category": "movie", "title": f"新电影{i}", "creator": "导演", "year": 2020+i, "reason": "适合现在", "tags": ["科幻"], "mood_fit": ["获得灵感"], "energy_level": "medium", "duration_minutes": 90, "min_session_minutes": None}
            for i in range(1, 7)
        ]


class FakeMetadata:
    def __init__(self): self.search_calls = []
    def search(self, category, query, limit=8):
        self.search_calls.append(query)
        number = query[-1]
        return [MetadataCandidate(source="tmdb", external_id=number, category=category, title=query, year=2020+int(number), creators=["导演"], raw={})]
    def draft(self, category, external_id):
        return CardDraft(category=category, title=f"新电影{external_id}", source="tmdb", external_id=external_id, duration_minutes=90, tags=["科幻"])


class WorkflowTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "workflow.db")
        self.db.initialize()
        self.metadata = FakeMetadata()
        self.workflow = DecisionWorkflow(self.db, ai=FakeAI(), metadata=self.metadata)
        self.context = DecisionContext(120, "medium", ["movie"], preferences=["科幻"])

    def tearDown(self): self.temp.cleanup()

    def add_cards(self, count):
        for i in range(count):
            self.db.add_card(Card(id=f"existing_{i}", category="movie", title=f"旧电影{i}", duration_minutes=90, tags=["科幻"], energy_level="medium"))

    def test_shelf_first_explores_when_count_is_three(self):
        self.add_cards(3)
        result = self.workflow.decide(self.context, "shelf_first")
        self.assertEqual(result.fallback_reason, "low_count")
        self.assertIsNotNone(result.shelf_recommendation)
        self.assertEqual(len(result.exploration_suggestions), 3)
        self.assertTrue(all(item.verified for item in result.exploration_suggestions))

    def test_shelf_first_does_not_explore_with_four_good_matches(self):
        self.add_cards(4)
        result = self.workflow.decide(self.context, "shelf_first")
        self.assertIsNone(result.fallback_reason)
        self.assertEqual(result.exploration_suggestions, [])

    def test_shelf_first_explores_when_top_fit_is_below_sixty(self):
        for i in range(4):
            self.db.add_card(
                Card(
                    id=f"hard_{i}", category="movie", title=f"费脑电影{i}",
                    duration_minutes=110, energy_level="high", tags=["沉重"],
                )
            )
        low_context = DecisionContext(120, "low", ["movie"], preferences=["轻松愉悦"])
        result = self.workflow.decide(low_context, "shelf_first")
        self.assertEqual(result.fallback_reason, "low_fit")
        self.assertLess(result.top_fit_score, 60)

    def test_free_mode_does_not_return_shelf_candidate(self):
        self.add_cards(1)
        result = self.workflow.decide(self.context, "free")
        self.assertIsNone(result.shelf_recommendation)
        self.assertEqual(len(result.exploration_suggestions), 3)

    def test_exploration_scores_all_generated_candidates_before_top_three(self):
        result = self.workflow.decide(self.context, "free")
        self.assertEqual(len(self.metadata.search_calls), 6)
        self.assertTrue(result.exploration_suggestions[0].is_best)
        self.assertEqual(result.exploration_suggestions[0].fit_score, max(x.fit_score for x in result.exploration_suggestions))

    def test_resolve_add_start_and_dismiss(self):
        result = self.workflow.decide(self.context, "free")
        added = self.workflow.resolve(result.exploration_suggestions[0].id, "add")
        self.assertEqual(added.status, "todo")
        started = self.workflow.resolve(result.exploration_suggestions[1].id, "start")
        self.assertEqual(started.status, "in_progress")
        dismissed = self.workflow.resolve(result.exploration_suggestions[2].id, "dismiss")
        self.assertIsNone(dismissed)

    def test_unverified_game_requires_confirmation(self):
        from decision_shelf.models import ExplorationSuggestion

        session = self.db.save_decision(self.context, [], decision_scope="free")
        suggestion = ExplorationSuggestion(
            id="game_suggestion", session_id=session,
            draft=CardDraft(category="game", title="一个游戏", source="ai", min_session_minutes=30),
            verified=False, fit_score=70, reason="适合放松",
        )
        self.db.add_exploration_suggestions([suggestion])
        with self.assertRaises(ValueError):
            self.workflow.resolve(suggestion.id, "add")
        card = self.workflow.resolve(suggestion.id, "add", confirmed=True)
        self.assertEqual(card.title, "一个游戏")


if __name__ == "__main__": unittest.main()
