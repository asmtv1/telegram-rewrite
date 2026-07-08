import pytest
from cryptography.fernet import Fernet


@pytest.mark.asyncio
async def test_publish_sends_plain_text_chunks_with_parse_mode_disabled(tmp_path):
    from app.config import Settings
    from app.services.telegram import TELEGRAM_TEXT_LIMIT, TelegramService

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        session_secret="test-session-secret",
        app_encryption_key=Fernet.generate_key().decode("utf-8"),
        telegram_api_id=123456,
        telegram_api_hash="test-api-hash",
        telegram_sessions_dir=str(tmp_path / "sessions"),
        media_dir=str(tmp_path / "media"),
    )
    service = TelegramService(settings)
    calls = []

    class FakeClient:
        async def is_user_authorized(self):
            return True

        async def send_message(self, target, text, parse_mode=None):
            calls.append(("message", target, text, parse_mode))

    async def noop(*args, **kwargs):
        return None

    service._require_credentials = noop
    service._connect = noop
    service._disconnect = noop
    service._ensure_can_publish = noop
    service._app_client = lambda user_id: FakeClient()

    await service.publish(None, "user1", "@target", "x" * (TELEGRAM_TEXT_LIMIT + 1), [])

    assert [call[0] for call in calls] == ["message", "message"]
    assert [len(call[2]) for call in calls] == [TELEGRAM_TEXT_LIMIT, 1]
    assert all(call[3] is None for call in calls)


@pytest.mark.asyncio
async def test_publish_sends_media_caption_with_parse_mode_disabled_and_caption_limit(tmp_path):
    from app.config import Settings
    from app.services.telegram import TELEGRAM_CAPTION_LIMIT, TelegramService

    media_dir = tmp_path / "media"
    media_dir.mkdir()
    image_path = media_dir / "image.jpg"
    image_path.write_bytes(b"image")
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        session_secret="test-session-secret",
        app_encryption_key=Fernet.generate_key().decode("utf-8"),
        telegram_api_id=123456,
        telegram_api_hash="test-api-hash",
        telegram_sessions_dir=str(tmp_path / "sessions"),
        media_dir=str(media_dir),
    )
    service = TelegramService(settings)
    calls = []

    class FakeClient:
        async def is_user_authorized(self):
            return True

        async def send_file(self, target, files, caption=None, parse_mode=None):
            calls.append(("file", target, files, caption, parse_mode))

    async def noop(*args, **kwargs):
        return None

    service._require_credentials = noop
    service._connect = noop
    service._disconnect = noop
    service._ensure_can_publish = noop
    service._app_client = lambda user_id: FakeClient()

    text = ("Первое предложение. Второе предложение. " * 80).strip()

    await service.publish(None, "user1", "@target", text, ["/media/image.jpg"])

    assert len(calls) == 1
    assert calls[0][0] == "file"
    assert len(calls[0][3]) <= TELEGRAM_CAPTION_LIMIT
    assert calls[0][3].endswith(".")
    assert calls[0][4] is None


@pytest.mark.asyncio
async def test_publish_returns_first_message_id_and_public_url(tmp_path):
    from app.config import Settings
    from app.services.telegram import TelegramService

    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        session_secret="test-session-secret",
        app_encryption_key=Fernet.generate_key().decode("utf-8"),
        telegram_api_id=123456,
        telegram_api_hash="test-api-hash",
        telegram_sessions_dir=str(tmp_path / "sessions"),
        media_dir=str(tmp_path / "media"),
    )
    service = TelegramService(settings)

    class FakeMessage:
        id = 4321

    class FakeClient:
        async def is_user_authorized(self):
            return True

        async def send_message(self, target, text, parse_mode=None):
            return FakeMessage()

    async def noop(*args, **kwargs):
        return None

    service._require_credentials = noop
    service._connect = noop
    service._disconnect = noop
    service._ensure_can_publish = noop
    service._app_client = lambda user_id: FakeClient()

    result = await service.publish(None, "user1", "@target", "text", [])

    assert result.message_id == 4321
    assert result.url == "https://t.me/target/4321"
