from conftest import login


def test_secure_session_setting_marks_login_cookie_secure(test_settings, monkeypatch):
    from cryptography.fernet import Fernet
    from fastapi.testclient import TestClient

    monkeypatch.setenv("SESSION_SECRET", test_settings.session_secret)
    monkeypatch.setenv("APP_ENCRYPTION_KEY", test_settings.app_encryption_key)
    monkeypatch.setenv("DATABASE_URL", test_settings.database_url)
    monkeypatch.setenv("TELEGRAM_SESSIONS_DIR", test_settings.telegram_sessions_dir)
    monkeypatch.setenv("MEDIA_DIR", test_settings.media_dir)
    monkeypatch.setenv("MEDIA_URL_PREFIX", test_settings.media_url_prefix)
    from app.main import create_app
    from app.services.deepseek import FakeRewriteService
    from app.services.telegram import FakeTelegramService

    secure_settings = test_settings.model_copy(
        update={
            "session_secret": "secure-session-secret",
            "app_encryption_key": Fernet.generate_key().decode("utf-8"),
            "session_cookie_secure": True,
        }
    )
    app = create_app(
        settings=secure_settings,
        telegram_service=FakeTelegramService(),
        rewrite_service=FakeRewriteService("rewritten text"),
    )

    with TestClient(app) as test_client:
        response = test_client.post(
            "/api/auth/login",
            json={"username": "user1", "password": "12345"},
        )

    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


def test_valid_login_sets_current_user(client):
    login(client, "user1", "12345")

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": "user1"}


def test_invalid_login_is_rejected(client):
    response = client.post(
        "/api/auth/login",
        json={"username": "user1", "password": "wrong"},
    )

    assert response.status_code == 401


def test_protected_endpoint_without_cookie_is_rejected(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"
