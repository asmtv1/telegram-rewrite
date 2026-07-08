import pytest


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("@source_channel", "source_channel"),
        ("https://t.me/source_channel/123", "source_channel"),
        ("t.me/source_channel", "source_channel"),
        ("t.me/c/123456789/42", -100123456789),
        ("-100123456789", -100123456789),
    ],
)
def test_normalize_channel_accepts_user_facing_channel_inputs(raw, expected):
    from app.services.telegram import normalize_channel

    assert normalize_channel(raw) == expected


def test_normalize_channel_rejects_blank_channel():
    from app.services.telegram import TelegramServiceError, normalize_channel

    with pytest.raises(TelegramServiceError) as exc:
        normalize_channel(" @ ")

    assert exc.value.code == "telegram_channel_not_found"
    assert exc.value.status_code == 404


@pytest.mark.parametrize(
    ("error_factory", "status_code", "message_part"),
    [
        (lambda: __import__("telethon.errors").errors.UsernameInvalidError(request=None), 404, "Канал не найден"),
        (lambda: __import__("telethon.errors").errors.ChannelPrivateError(request=None), 403, "Нет доступа"),
        (lambda: __import__("telethon.errors").errors.ChatWriteForbiddenError(request=None), 403, "Нет прав"),
        (lambda: __import__("telethon.errors").errors.FloodWaitError(request=None, capture=17), 429, "17"),
    ],
)
def test_map_telegram_error_returns_stable_http_statuses(error_factory, status_code, message_part):
    from app.services.telegram import map_telegram_error

    mapped = map_telegram_error(error_factory(), "@source")

    assert mapped.status_code == status_code
    assert message_part in mapped.message


def test_build_publish_parts_splits_long_text_without_media():
    from app.services.telegram import TELEGRAM_TEXT_LIMIT, build_publish_parts

    text = "x" * (TELEGRAM_TEXT_LIMIT + 12)

    parts = build_publish_parts(text, has_media=False)

    assert [kind for kind, _ in parts] == ["text", "text"]
    assert len(parts[0][1]) == TELEGRAM_TEXT_LIMIT
    assert parts[1][1] == "x" * 12


def test_build_publish_parts_limits_media_caption_to_telegram_limit():
    from app.services.telegram import TELEGRAM_CAPTION_LIMIT, build_publish_parts

    text = ("Первое предложение. Второе предложение. " * 60).strip()

    parts = build_publish_parts(text, has_media=True)

    assert len(parts) == 1
    assert parts[0][0] == "media"
    assert len(parts[0][1]) <= TELEGRAM_CAPTION_LIMIT
    assert parts[0][1].endswith(".")
