import pytest

from conftest import login


async def insert_post(app, user_id: str) -> int:
    from app.db import get_session_maker
    from app.models import Post

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id=user_id,
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=101,
            original_text="original",
            publish_status="fetched",
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        return post.id


@pytest.mark.asyncio
async def test_user_cannot_rewrite_another_users_post(app, client):
    post_id = await insert_post(app, "user2")
    login(client, "user1", "12345")

    response = client.post(f"/api/posts/{post_id}/rewrite", json={"prompt": "rewrite"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_user_cannot_publish_another_users_post(app, client):
    post_id = await insert_post(app, "user2")
    login(client, "user1", "12345")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={"target_channel": "@target", "text": "manual edit"},
    )

    assert response.status_code == 404


def test_posts_fetch_returns_membership_error_message(app, client):
    from app.services.telegram import TelegramServiceError

    class NotMemberTelegramService:
        async def fetch_text_posts(self, session, user_id, source_channel, offset_id):
            raise TelegramServiceError(
                "telegram_not_channel_member",
                "Вы не состоите в этом Telegram-канале. Сначала подпишитесь на канал, затем повторите загрузку.",
            )

    app.state.telegram_service = NotMemberTelegramService()
    login(client, "user1", "12345")

    response = client.get("/api/posts?source_channel=@source&target_channel=@target")

    assert response.status_code == 400
    assert "подпишитесь" in response.json()["detail"]


def test_posts_fetch_does_not_require_target_channel(app, client):
    from app.services.telegram import TextPage, TextPost

    class SourceOnlyTelegramService:
        async def fetch_text_posts(self, session, user_id, source_channel, offset_id):
            assert source_channel == "@source"
            return TextPage(
                items=[TextPost(id=11, text="source text")],
                next_offset_id=11,
                has_more=False,
            )

    app.state.telegram_service = SourceOnlyTelegramService()
    login(client, "user1", "12345")

    response = client.get("/api/posts?source_channel=@source")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0]["target_channel"] is None
    assert payload["items"][0]["original_text"] == "source text"


def test_posts_fetch_returns_media_urls(app, client):
    from app.services.telegram import TextPage, TextPost

    class MediaTelegramService:
        async def fetch_text_posts(self, session, user_id, source_channel, offset_id):
            return TextPage(
                items=[TextPost(id=12, text="caption", media_urls=["/media/posts/user1/source/12.jpg"])],
                next_offset_id=12,
                has_more=False,
            )

    app.state.telegram_service = MediaTelegramService()
    login(client, "user1", "12345")

    response = client.get("/api/posts?source_channel=@source")

    assert response.status_code == 200
    assert response.json()["items"][0]["media_urls"] == ["/media/posts/user1/source/12.jpg"]


@pytest.mark.asyncio
async def test_publish_passes_post_media_urls_to_telegram_service(app, client):
    from app.db import get_session_maker
    from app.models import Post

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id="user1",
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=301,
            original_text="original",
            publish_status="rewritten",
            media_urls=["/media/posts/user1/source/301.jpg"],
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        post_id = post.id

    class PublishTelegramService:
        def __init__(self):
            self.calls = []

        async def publish(self, session, user_id, target_channel, text, media_urls):
            self.calls.append((user_id, target_channel, text, media_urls))

    service = PublishTelegramService()
    app.state.telegram_service = service
    login(client, "user1", "12345")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={"target_channel": "@target", "text": "manual edit"},
    )

    assert response.status_code == 200
    assert service.calls == [
        ("user1", "@target", "manual edit", ["/media/posts/user1/source/301.jpg"])
    ]


@pytest.mark.asyncio
async def test_publish_can_skip_original_post_media(app, client):
    from app.db import get_session_maker
    from app.models import Post

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id="user1",
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=302,
            original_text="original",
            publish_status="rewritten",
            media_urls=["/media/posts/user1/source/302.jpg"],
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        post_id = post.id

    class PublishTelegramService:
        def __init__(self):
            self.calls = []

        async def publish(self, session, user_id, target_channel, text, media_urls):
            self.calls.append((user_id, target_channel, text, media_urls))

    service = PublishTelegramService()
    app.state.telegram_service = service
    login(client, "user1", "12345")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={"target_channel": "@target", "text": "manual edit", "media_urls": []},
    )

    assert response.status_code == 200
    assert service.calls == [("user1", "@target", "manual edit", [])]


@pytest.mark.asyncio
async def test_upload_custom_media_can_be_published_with_original_media(app, client):
    from app.db import get_session_maker
    from app.models import Post

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id="user1",
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=303,
            original_text="original",
            publish_status="rewritten",
            media_urls=["/media/posts/user1/source/303.jpg"],
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        post_id = post.id

    class PublishTelegramService:
        def __init__(self):
            self.calls = []

        async def publish(self, session, user_id, target_channel, text, media_urls):
            self.calls.append((user_id, target_channel, text, media_urls))

    service = PublishTelegramService()
    app.state.telegram_service = service
    login(client, "user1", "12345")

    upload_response = client.post(
        f"/api/posts/{post_id}/media",
        files=[("files", ("custom.jpg", b"image-bytes", "image/jpeg"))],
    )

    assert upload_response.status_code == 200
    uploaded_urls = upload_response.json()["media_urls"]
    assert len(uploaded_urls) == 1
    assert uploaded_urls[0].startswith("/media/uploads/user1/")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={
            "target_channel": "@target",
            "text": "manual edit",
            "media_urls": ["/media/posts/user1/source/303.jpg", uploaded_urls[0]],
        },
    )

    assert response.status_code == 200
    assert service.calls == [
        ("user1", "@target", "manual edit", ["/media/posts/user1/source/303.jpg", uploaded_urls[0]])
    ]


@pytest.mark.asyncio
async def test_history_returns_published_media_urls(app, client):
    from app.db import get_session_maker
    from app.models import Post

    session_maker = get_session_maker(app)
    async with session_maker() as session:
        post = Post(
            user_id="user1",
            source_channel="@source",
            target_channel="@target",
            telegram_message_id=304,
            original_text="original",
            publish_status="rewritten",
            media_urls=["/media/posts/user1/source/304.jpg"],
        )
        session.add(post)
        await session.commit()
        await session.refresh(post)
        post_id = post.id

    class PublishTelegramService:
        async def publish(self, session, user_id, target_channel, text, media_urls):
            return None

    app.state.telegram_service = PublishTelegramService()
    login(client, "user1", "12345")

    publish_response = client.post(
        f"/api/posts/{post_id}/publish",
        json={
            "target_channel": "@target",
            "text": "manual edit",
            "media_urls": ["/media/uploads/user1/304/custom.jpg"],
        },
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["published_media_urls"] == ["/media/uploads/user1/304/custom.jpg"]

    history_response = client.get("/api/posts/history")

    assert history_response.status_code == 200
    assert history_response.json()["items"][0]["published_media_urls"] == [
        "/media/uploads/user1/304/custom.jpg"
    ]
    assert history_response.json()["items"][0]["media_urls"] == ["/media/posts/user1/source/304.jpg"]


def test_posts_history_returns_only_processed_posts_for_current_user(app, client):
    from app.db import get_session_maker
    from app.models import Post

    async def seed():
        session_maker = get_session_maker(app)
        async with session_maker() as session:
            session.add_all(
                [
                    Post(
                        user_id="user1",
                        source_channel="@source",
                        target_channel="@target",
                        telegram_message_id=201,
                        original_text="original rewritten",
                        rewritten_text="rewritten",
                        publish_status="rewritten",
                    ),
                    Post(
                        user_id="user1",
                        source_channel="@source",
                        target_channel=None,
                        telegram_message_id=202,
                        original_text="only fetched",
                        publish_status="fetched",
                    ),
                    Post(
                        user_id="user2",
                        source_channel="@source",
                        target_channel="@target",
                        telegram_message_id=203,
                        original_text="other user",
                        rewritten_text="other rewritten",
                        publish_status="rewritten",
                    ),
                ]
            )
            await session.commit()

    import anyio

    anyio.run(seed)
    login(client, "user1", "12345")

    response = client.get("/api/posts/history")

    assert response.status_code == 200
    payload = response.json()
    assert [item["original_text"] for item in payload["items"]] == ["original rewritten"]
    assert payload["items"][0]["created_at"]
    assert payload["items"][0]["updated_at"]
    assert payload["items"][0]["published_at"] is None


@pytest.mark.asyncio
async def test_publish_sets_published_at_and_returns_timestamps(app, client):
    post_id = await insert_post(app, "user1")

    class PublishTelegramService:
        async def publish(self, session, user_id, target_channel, text, media_urls):
            return None

    app.state.telegram_service = PublishTelegramService()
    login(client, "user1", "12345")

    response = client.post(
        f"/api/posts/{post_id}/publish",
        json={"target_channel": "@target", "text": "manual edit"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["publish_status"] == "published"
    assert payload["published_at"]
    assert payload["updated_at"]
