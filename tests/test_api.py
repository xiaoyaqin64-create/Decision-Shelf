from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from decision_shelf.database import Database
from decision_shelf.webapp import create_app


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "api.db")
        self.client = TestClient(create_app(self.db, static_dir=Path(self.temp.name) / "missing"))

    def tearDown(self): self.temp.cleanup()

    def test_card_crud_decision_and_action(self):
        created = self.client.post("/api/cards", json={
            "category": "movie", "title": "测试电影", "duration_minutes": 90,
            "tags": ["科幻"], "energy_level": "medium", "mood_fit": ["获得灵感"],
        })
        self.assertEqual(created.status_code, 201)
        card_id = created.json()["id"]
        self.assertEqual(len(self.client.get("/api/cards").json()["items"]), 1)
        decision = self.client.post("/api/decisions", json={
            "available_minutes": 120, "energy_level": "medium", "categories": ["movie"],
            "preferences": ["科幻"], "scope": "shelf_only",
        })
        self.assertEqual(decision.status_code, 200)
        self.assertEqual(decision.json()["shelf_recommendation"]["card_id"], card_id)
        action = self.client.post(f"/api/cards/{card_id}/actions", json={"action": "start"})
        self.assertEqual(action.json()["status"], "in_progress")

    def test_duplicate_external_card_is_overwritten_without_new_row(self):
        payload = {"category": "movie", "title": "A", "source": "tmdb", "external_id": "1"}
        self.assertEqual(self.client.post("/api/cards", json=payload).status_code, 201)
        response = self.client.post("/api/cards", json={**payload, "description": "更新后的简介"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["upsert_result"], "overwritten")
        self.assertEqual(response.json()["description"], "更新后的简介")
        self.assertEqual(len(self.client.get("/api/cards").json()["items"]), 1)

    def test_recycle_restore_and_time_entries(self):
        card = self.client.post("/api/cards", json={"category":"book","title":"时间之书","min_session_minutes":25}).json()
        entry = self.client.post(f"/api/cards/{card['id']}/time-entries", json={"minutes":40,"note":"第一章"})
        self.assertEqual(entry.json()["total_minutes"], 40)
        self.assertEqual(self.client.delete(f"/api/cards/{card['id']}").json()["status"], "removed")
        self.assertEqual(self.client.post(f"/api/cards/{card['id']}/restore").json()["status"], "todo")

    def test_same_category_title_upsert_preserves_progress_and_time(self):
        first = self.client.post("/api/cards", json={"category":"game","title":"星 海","min_session_minutes":20}).json()
        self.client.post(f"/api/cards/{first['id']}/actions", json={"action":"start"})
        self.client.post(f"/api/cards/{first['id']}/time-entries", json={"minutes":35})
        second = self.client.post("/api/cards", json={"category":"game","title":"星海","description":"新资料","min_session_minutes":30}).json()
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["status"], "in_progress")
        self.assertEqual(second["description"], "新资料")
        self.assertEqual(self.client.get(f"/api/cards/{first['id']}/time-entries").json()["total_minutes"], 35)

    def test_validation_error_is_stable(self):
        response = self.client.post("/api/decisions", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "invalid_input")

    def test_theme_color_batch_resolve_uses_fallback_without_image(self):
        card = self.client.post("/api/cards", json={"category":"movie","title":"无海报电影"}).json()
        response = self.client.post("/api/cards/theme-colors/resolve", json={"card_ids":[card["id"]]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["source"], "fallback")
        saved = self.client.get(f"/api/cards/{card['id']}").json()
        self.assertRegex(saved["theme_color"], r"^#[0-9A-F]{6}$")


if __name__ == "__main__": unittest.main()
