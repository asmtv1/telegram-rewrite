import pytest
from cryptography.fernet import Fernet


def _settings(tmp_path):
    from app.config import Settings

    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        session_secret="test-session-secret",
        app_encryption_key=Fernet.generate_key().decode("utf-8"),
        telegram_api_id=123456,
        telegram_api_hash="test-api-hash",
        telegram_sessions_dir=str(tmp_path / "sessions"),
        media_dir=str(tmp_path / "media"),
    )


@pytest.mark.asyncio
async def test_download_message_photos_skips_non_photo_media(tmp_path):
    from app.services.telegram import TelegramService

    service = TelegramService(_settings(tmp_path))

    class FakeClient:
        async def download_media(self, message, file):
            raise AssertionError("non-photo media must not be downloaded")

    class FakeVideoMessage:
        id = 10
        photo = object()
        media = object()

    assert await service._download_message_photos(FakeClient(), "user1", "@source", FakeVideoMessage()) == []


@pytest.mark.asyncio
async def test_download_message_photos_reuses_existing_file(tmp_path, monkeypatch):
    from app.services.telegram import TelegramService

    monkeypatch.setattr("app.services.telegram.MessageMediaPhoto", object)
    service = TelegramService(_settings(tmp_path))
    directory = tmp_path / "media" / "posts" / "user1" / "-100123"
    directory.mkdir(parents=True)
    existing = directory / "42.jpg"
    existing.write_bytes(b"already downloaded")

    class FakeClient:
        async def download_media(self, message, file):
            raise AssertionError("existing media must not be downloaded again")

    class FakePhotoMessage:
        id = 42
        media = object()

    assert await service._download_message_photos(FakeClient(), "user1", "-100123", FakePhotoMessage()) == [
        "/media/posts/user1/-100123/42.jpg"
    ]
