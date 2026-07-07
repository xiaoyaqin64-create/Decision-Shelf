from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping

# Avoid discovering Linux/macOS keyring entry points in a frozen Windows app
# (and vice versa). The selected backend remains the operating-system vault.
IS_ANDROID = os.getenv("DECISION_SHELF_PLATFORM") == "android"

if not IS_ANDROID and sys.platform == "win32":
    os.environ.setdefault(
        "PYTHON_KEYRING_BACKEND", "keyring.backends.Windows.WinVaultKeyring"
    )
elif not IS_ANDROID and sys.platform == "darwin":
    os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.macOS.Keyring")

if not IS_ANDROID:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
else:  # Chaquopy provides the java module at runtime.
    keyring = None  # type: ignore[assignment]

    class KeyringError(Exception):
        pass

    class PasswordDeleteError(KeyringError):
        pass


KEYRING_SERVICE = "Decision Shelf"
SECRET_KEYS = {
    "DEEPSEEK_API_KEY": "deepseek-api-key",
    "TMDB_READ_ACCESS_TOKEN": "tmdb-read-access-token",
}
PLAIN_KEYS = (
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "MUSICBRAINZ_CONTACT",
)
DEFAULTS = {
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "MUSICBRAINZ_CONTACT": "",
}


class CredentialStoreError(RuntimeError):
    pass


def _android_store():
    from java import jclass  # type: ignore[import-not-found]

    return jclass("com.decisionshelf.app.SecretStore")


def _get_secret(account: str) -> str | None:
    if IS_ANDROID:
        try:
            value = _android_store().get(account)
            return str(value) if value else None
        except Exception as exc:
            raise KeyringError(str(exc)) from exc
    return keyring.get_password(KEYRING_SERVICE, account)


def _set_secret(account: str, value: str) -> None:
    if IS_ANDROID:
        try:
            _android_store().set(account, value)
        except Exception as exc:
            raise KeyringError(str(exc)) from exc
    else:
        keyring.set_password(KEYRING_SERVICE, account, value)


def _delete_secret(account: str) -> None:
    if IS_ANDROID:
        try:
            _android_store().delete(account)
        except Exception as exc:
            raise KeyringError(str(exc)) from exc
    else:
        keyring.delete_password(KEYRING_SERVICE, account)


def config_path() -> Path:
    return Path(os.getenv("DECISION_SHELF_CONFIG", "settings.json"))


def load_user_settings(path: Path | None = None) -> None:
    """Load non-secret JSON settings and secrets from the operating-system vault."""
    target = path or config_path()
    if target.exists():
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            for key in PLAIN_KEYS:
                value = payload.get(key)
                if isinstance(value, str):
                    os.environ[key] = value

    for env_key, account in SECRET_KEYS.items():
        try:
            value = _get_secret(account)
        except KeyringError:
            continue
        if value:
            os.environ[env_key] = value


def public_settings() -> dict[str, object]:
    """Return settings safe for the browser. Secret values are never included."""
    return {
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY", "").strip()),
        "deepseek_base_url": os.getenv(
            "DEEPSEEK_BASE_URL", DEFAULTS["DEEPSEEK_BASE_URL"]
        ),
        "deepseek_model": os.getenv("DEEPSEEK_MODEL", DEFAULTS["DEEPSEEK_MODEL"]),
        "tmdb_configured": bool(os.getenv("TMDB_READ_ACCESS_TOKEN", "").strip()),
        "musicbrainz_contact": os.getenv("MUSICBRAINZ_CONTACT", ""),
        "secret_storage": "system",
    }


def save_user_settings(values: Mapping[str, str], path: Path | None = None) -> None:
    """Persist ordinary values to JSON and secrets to Credential Manager/Keychain."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    plain = {key: os.getenv(key, DEFAULTS[key]) for key in PLAIN_KEYS}
    for key in PLAIN_KEYS:
        if key in values:
            plain[key] = values[key].strip()
    target.write_text(
        json.dumps(plain, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for key, value in plain.items():
        os.environ[key] = value

    for env_key, account in SECRET_KEYS.items():
        if env_key not in values:
            continue
        value = values[env_key].strip()
        try:
            if value:
                _set_secret(account, value)
            else:
                try:
                    _delete_secret(account)
                except PasswordDeleteError:
                    pass
        except KeyringError as exc:
            raise CredentialStoreError(
                "系统凭据库不可用，密钥未保存。请确认系统钥匙串服务可以正常访问。"
            ) from exc
        if value:
            os.environ[env_key] = value
        else:
            os.environ.pop(env_key, None)
