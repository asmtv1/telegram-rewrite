import pytest

from conftest import login


def test_posts_fetch_uses_mapped_telegram_error_status(app, client):
    from app.services.telegram import TelegramServiceError

    class MissingChannelTelegramService:
        async def fetch_text_posts(self, session, user_id, source_channel, offset_id):
            raise TelegramServiceError(
                "telegram_channel_not_found",
                "Канал не найден (@missing). Проверьте имя или ссылку",
                status_code=404,
            )

    app.state.telegram_service = MissingChannelTelegramService()
    login(client, "user1", "12345")

    response = client.get("/api/posts?source_channel=@missing")

    assert response.status_code == 404
    assert "Канал не найден" in response.json()["detail"]


@pytest.mark.asyncio
async def test_publish_uses_mapped_telegram_error_status(app, client):
    from app.db import get_session_maker
    from app.models import Post
    from app.services.telegram import TelegramServiceError

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id="user1",
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=401,
            original_text="original",
            publish_status="rewritten",
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        post_id = post.id

    class FloodWaitTelegramService:
        async def publish(self, session, user_id, target_channel, text, media_urls):
            raise TelegramServiceError(
                "telegram_flood_wait",
                "Telegram просит подождать 19 сек и повторить запрос",
                status_code=429,
            )

    app.state.telegram_service = FloodWaitTelegramService()
    login(client, "user1", "12345")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={"target_channel": "@target", "text": "manual edit"},
    )

    assert response.status_code == 429
    assert "19" in response.json()["detail"]
