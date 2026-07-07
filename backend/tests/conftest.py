import os

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient


@pytest.fixture
def test_settings(tmp_path):
    from app.config import Settings

    db_path = tmp_path / "test.db"
    sessions_dir = tmp_path / "sessions"
    media_dir = tmp_path / "media"
    sessions_dir.mkdir()
    media_dir.mkdir()

    return Settings(
        database_url=f"sqlite+aiosqlite:///{db_path}",
        session_secret="test-session-secret",
        app_users="user1:12345,user2:2407041",
        deepseek_api_key="test-deepseek-key",
        app_encryption_key=Fernet.generate_key().decode("utf-8"),
        telegram_api_id=123456,
        telegram_api_hash="test-api-hash",
        telegram_sessions_dir=str(sessions_dir),
        media_dir=str(media_dir),
    )


@pytest.fixture
def app(test_settings):
    os.environ["SESSION_SECRET"] = test_settings.session_secret
    os.environ["APP_ENCRYPTION_KEY"] = test_settings.app_encryption_key
    os.environ["DATABASE_URL"] = test_settings.database_url
    os.environ["TELEGRAM_SESSIONS_DIR"] = test_settings.telegram_sessions_dir
    os.environ["MEDIA_DIR"] = test_settings.media_dir
    os.environ["MEDIA_URL_PREFIX"] = test_settings.media_url_prefix
    from app.main import create_app
    from app.services.deepseek import FakeRewriteService
    from app.services.telegram import FakeTelegramService

    return create_app(
        settings=test_settings,
        telegram_service=FakeTelegramService(),
        rewrite_service=FakeRewriteService("rewritten text"),
    )


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, username: str = "user1", password: str = "12345") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
