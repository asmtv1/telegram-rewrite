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


@pytest.mark.asyncio
async def test_fetch_text_posts_combines_all_photos_from_grouped_post(tmp_path, test_settings, monkeypatch):
    from app.models import TelegramCredentials
    from app.services.telegram import TelegramService

    monkeypatch.setattr("app.services.telegram.MessageMediaPhoto", object)

    class FakePhotoMessage:
        def __init__(self, message_id, text):
            self.id = message_id
            self.message = text
            self.media = object()
            self.grouped_id = 9001

    class FakeClient:
        async def connect(self):
            return None

        async def disconnect(self):
            return None

        async def is_user_authorized(self):
            return True

        async def get_permissions(self, channel, user):
            return object()

        async def download_media(self, message, file):
            path = f"{file}.jpg"
            with open(path, "wb") as media_file:
                media_file.write(b"image")
            return path

        async def iter_messages(self, *args, **kwargs):
            yield FakePhotoMessage(102, "")
            yield FakePhotoMessage(101, "caption")

    client = FakeClient()

    class TestTelegramService(TelegramService):
        def _app_client(self, user_id):
            return client

        async def _require_credentials(self, session, user_id):
            return TelegramCredentials(user_id=user_id, phone="+79990000000")

    service = TestTelegramService(test_settings)

    page = await service.fetch_text_posts(object(), "user1", "@source", None)

    assert len(page.items) == 1
    assert page.items[0].text == "caption"
    assert page.items[0].media_urls == [
        "/media/posts/user1/source/101.jpg",
        "/media/posts/user1/source/102.jpg",
    ]
