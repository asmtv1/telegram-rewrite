import pytest


@pytest.mark.asyncio
async def test_collect_text_posts_returns_ten_text_messages_and_next_offset():
    from app.services.telegram import RawTelegramMessage, collect_text_posts

    raw_messages = [
        RawTelegramMessage(id=120 - index, text=("text" if index % 2 == 0 else ""))
        for index in range(30)
    ]

    page = await collect_text_posts(raw_messages, page_size=10, raw_scan_limit=100)

    assert len(page.items) == 10
    assert all(item.text == "text" for item in page.items)
    assert page.next_offset_id == page.items[-1].id
    assert page.has_more is True


@pytest.mark.asyncio
async def test_collect_text_posts_does_not_stop_on_media_only_prefix():
    from app.services.telegram import RawTelegramMessage, collect_text_posts

    raw_messages = [
        *[RawTelegramMessage(id=100 - index, text="") for index in range(20)],
        *[RawTelegramMessage(id=80 - index, text=f"text {index}") for index in range(3)],
    ]

    page = await collect_text_posts(raw_messages, page_size=10, raw_scan_limit=100)

    assert [item.text for item in page.items] == ["text 0", "text 1", "text 2"]
    assert page.has_more is False
