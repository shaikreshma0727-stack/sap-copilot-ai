"""The server must not start with a weak JWT secret."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_sap_copilot_secret.db")
os.environ.setdefault("GROQ_API_KEY", "")
os.environ.setdefault("JWT_SECRET", "test-secret-test-secret-test-secret-123456")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings, validate_jwt_secret  # noqa: E402
from app.main import app  # noqa: E402


@pytest.mark.parametrize("weak", ["", "change-me", "change-me-generate-a-long-random-string", "short-secret", "x" * 31])
def test_weak_secrets_are_rejected(weak):
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        validate_jwt_secret(weak)


def test_strong_secret_is_accepted():
    validate_jwt_secret("a" * 32)
    validate_jwt_secret("k" * 40)


def test_server_refuses_to_start_with_a_weak_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "change-me")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="JWT_SECRET"):
            with TestClient(app):
                pass
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
