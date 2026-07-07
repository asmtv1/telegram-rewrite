from conftest import login


class PhoneOnlyTelegramService:
    def __init__(self):
        self.sent_to = None

    async def status(self, session, user_id):
        return False, None

    async def send_code(self, session, user_id, phone):
        self.sent_to = (user_id, phone)


class NonInteractiveFakeSentCode:
    phone_code_hash = "hash"
    timeout = 300


class NonInteractiveFakeClient:
    def __init__(self):
        self.connected = False
        self.disconnected = False
        self.sent_phone = None

    async def __aenter__(self):
        raise AssertionError("Telegram login flow must not use async context manager")

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True

    async def send_code_request(self, phone):
        self.sent_phone = phone
        return NonInteractiveFakeSentCode()


def test_send_code_uses_app_telegram_credentials_and_accepts_only_phone(test_settings):
    import os

    os.environ.setdefault("SESSION_SECRET", test_settings.session_secret)
    os.environ.setdefault("APP_ENCRYPTION_KEY", test_settings.app_encryption_key)
    os.environ.setdefault("DATABASE_URL", test_settings.database_url)
    os.environ.setdefault("TELEGRAM_SESSIONS_DIR", test_settings.telegram_sessions_dir)

    from app.main import create_app

    telegram_service = PhoneOnlyTelegramService()
    app = create_app(settings=test_settings, telegram_service=telegram_service)

    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        login(client, "user1", "12345")
        response = client.post("/api/telegram/send-code", json={"phone": "+79990000000"})

    assert response.status_code == 200
    assert telegram_service.sent_to == ("user1", "+79990000000")


async def test_telegram_service_send_code_connects_without_interactive_start(test_settings):
    from app.services.telegram import TelegramService

    client = NonInteractiveFakeClient()

    class TestTelegramService(TelegramService):
        def _app_client(self, user_id):
            return client

    service = TestTelegramService(test_settings)

    class FakeSession:
        async def merge(self, state):
            self.state = state

        async def commit(self):
            self.committed = True

    session = FakeSession()

    await service.send_code(session, "user1", "+79990000000")

    assert client.connected is True
    assert client.disconnected is True
    assert client.sent_phone == "+79990000000"


async def test_fetch_posts_requires_membership_before_reading_history(test_settings):
    from app.services.telegram import TelegramService, TelegramServiceError
    from app.models import TelegramCredentials
    from telethon.errors import UserNotParticipantError

    class MembershipFakeClient:
        def __init__(self):
            self.permissions_checked = False
            self.iter_messages_called = False

        async def connect(self):
            return None

        async def disconnect(self):
            return None

        async def is_user_authorized(self):
            return True

        async def get_permissions(self, channel, user):
            self.permissions_checked = True
            assert channel == "@source"
            assert user == "me"
            raise UserNotParticipantError(None)

        def iter_messages(self, *args, **kwargs):
            self.iter_messages_called = True
            raise AssertionError("history must not be read before membership check passes")

    client = MembershipFakeClient()

    class TestTelegramService(TelegramService):
        def _app_client(self, user_id):
            return client

        async def _require_credentials(self, session, user_id):
            return TelegramCredentials(user_id=user_id, phone="+79990000000")

    service = TestTelegramService(test_settings)

    try:
        await service.fetch_text_posts(object(), "user1", "@source", None)
    except TelegramServiceError as exc:
        assert exc.code == "telegram_not_channel_member"
        assert "подпишитесь" in exc.message
    else:
        raise AssertionError("expected telegram_not_channel_member")

    assert client.permissions_checked is True
    assert client.iter_messages_called is False


async def test_publish_checks_target_channel_posting_rights_before_sending(test_settings):
    from app.models import TelegramCredentials
    from app.services.telegram import TelegramService, TelegramServiceError

    class Permissions:
        is_chat = False
        is_admin = True
        post_messages = False

    class PublishPermissionFakeClient:
        def __init__(self):
            self.permissions_checked = False
            self.send_message_called = False

        async def connect(self):
            return None

        async def disconnect(self):
            return None

        async def is_user_authorized(self):
            return True

        async def get_permissions(self, channel, user):
            self.permissions_checked = True
            assert channel == "@target"
            assert user == "me"
            return Permissions()

        async def send_message(self, channel, text):
            self.send_message_called = True
            raise AssertionError("message must not be sent without post_messages rights")

    client = PublishPermissionFakeClient()

    class TestTelegramService(TelegramService):
        def _app_client(self, user_id):
            return client

        async def _require_credentials(self, session, user_id):
            return TelegramCredentials(user_id=user_id, phone="+79990000000")

    service = TestTelegramService(test_settings)

    try:
        await service.publish(object(), "user1", "@target", "text")
    except TelegramServiceError as exc:
        assert exc.code == "telegram_publish_forbidden"
        assert "нет прав на публикацию" in exc.message
    else:
        raise AssertionError("expected telegram_publish_forbidden")

    assert client.permissions_checked is True
    assert client.send_message_called is False
