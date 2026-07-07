from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from decision_shelf.app_paths import bundled_static_dir, user_data_dir
from decision_shelf.database import Database
from decision_shelf.settings import KEYRING_SERVICE, load_user_settings
from decision_shelf.webapp import create_app


class SettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(
            os.environ,
            {
                "DECISION_SHELF_CONFIG": str(self.root / "settings.json"),
                "DEEPSEEK_API_KEY": "",
                "TMDB_READ_ACCESS_TOKEN": "",
                "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                "DEEPSEEK_MODEL": "deepseek-v4-flash",
                "MUSICBRAINZ_CONTACT": "",
            },
        )
        self.env.start()
        self.secrets: dict[tuple[str, str], str] = {}
        self.get_password = patch(
            "decision_shelf.settings.keyring.get_password",
            side_effect=lambda service, account: self.secrets.get((service, account)),
        )
        self.set_password = patch(
            "decision_shelf.settings.keyring.set_password",
            side_effect=lambda service, account, value: self.secrets.__setitem__((service, account), value),
        )
        self.delete_password = patch(
            "decision_shelf.settings.keyring.delete_password",
            side_effect=lambda service, account: self.secrets.pop((service, account), None),
        )
        self.get_password.start()
        self.set_password.start()
        self.delete_password.start()
        db = Database(self.root / "api.db")
        self.client = TestClient(create_app(db, static_dir=self.root / "missing"))

    def tearDown(self):
        patch.stopall()
        self.temp.cleanup()

    def test_secrets_use_keyring_and_are_never_returned_or_written(self):
        response = self.client.put("/api/settings", json={
            "deepseek_api_key": "deep-secret",
            "deepseek_base_url": "https://example.invalid/v1",
            "deepseek_model": "test-model",
            "tmdb_read_access_token": "tmdb-secret",
            "musicbrainz_contact": "person@example.com",
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["deepseek_configured"])
        self.assertTrue(body["tmdb_configured"])
        self.assertNotIn("deep-secret", response.text)
        self.assertNotIn("tmdb-secret", response.text)
        self.assertEqual(
            self.secrets[(KEYRING_SERVICE, "deepseek-api-key")], "deep-secret"
        )
        config_text = (self.root / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn("secret", config_text)
        self.assertEqual(json.loads(config_text)["DEEPSEEK_MODEL"], "test-model")
        self.assertEqual(self.client.app.state.ai.client.config.api_key, "deep-secret")
        self.assertTrue(
            self.client.app.state.metadata.registry.get("movie").available
        )

    def test_empty_secret_keeps_existing_value_and_delete_removes_it(self):
        self.client.put("/api/settings", json={"deepseek_api_key": "keep-me"})
        self.client.put("/api/settings", json={"deepseek_api_key": ""})
        self.assertEqual(
            self.secrets[(KEYRING_SERVICE, "deepseek-api-key")], "keep-me"
        )
        response = self.client.delete("/api/settings/deepseek")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["deepseek_configured"])
        self.assertNotIn((KEYRING_SERVICE, "deepseek-api-key"), self.secrets)

    def test_load_combines_json_and_system_credentials(self):
        (self.root / "settings.json").write_text(
            json.dumps({
                "DEEPSEEK_BASE_URL": "https://custom.invalid",
                "DEEPSEEK_MODEL": "custom-model",
                "MUSICBRAINZ_CONTACT": "hello@example.com",
            }),
            encoding="utf-8",
        )
        self.secrets[(KEYRING_SERVICE, "deepseek-api-key")] = "loaded-secret"
        load_user_settings()
        self.assertEqual(os.environ["DEEPSEEK_MODEL"], "custom-model")
        self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "loaded-secret")

    def test_platform_user_data_locations(self):
        with patch.object(sys, "platform", "win32"), patch.dict(
            os.environ, {"LOCALAPPDATA": r"C:\Users\Friend\AppData\Local"}, clear=False
        ):
            os.environ.pop("DECISION_SHELF_HOME", None)
            self.assertEqual(
                user_data_dir(), Path(r"C:\Users\Friend\AppData\Local") / "Decision Shelf"
            )
        with patch.object(sys, "platform", "darwin"), patch.object(
            Path, "home", return_value=Path("/Users/friend")
        ):
            os.environ.pop("DECISION_SHELF_HOME", None)
            self.assertEqual(
                user_data_dir(),
                Path("/Users/friend/Library/Application Support/Decision Shelf"),
            )

    def test_bundled_static_uses_frozen_resource_root(self):
        with patch.object(sys, "_MEIPASS", str(self.root), create=True):
            self.assertEqual(bundled_static_dir(), self.root / "frontend" / "dist")


if __name__ == "__main__":
    unittest.main()
