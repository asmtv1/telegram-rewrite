import pytest
from cryptography.fernet import Fernet


@pytest.mark.asyncio
async def test_download_message_photos_skips_non_photo_media(tmp_path):
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

    class FakeClient:
        async def download_media(self, message, file):
            raise AssertionError("non-photo media must not be downloaded")

    class FakeVideoMessage:
        id = 10
        photo = object()
        media = object()

    assert await service._download_message_photos(FakeClient(), "user1", "@source", FakeVideoMessage()) == []
