import pytest


def test_strip_channel_references_removes_telegram_links_and_mentions_but_keeps_email():
    from app.services.deepseek import strip_channel_references

    text = "Пишите user@example.com, но не переходите в @source_news и https://t.me/source_news/42"

    assert strip_channel_references(text) == "Пишите user@example.com, но не переходите в и"


def test_clean_llm_response_removes_thinking_preamble_fences_and_outer_quotes():
    from app.services.deepseek import clean_llm_response

    raw = '<think>draft</think>\nВот переписанный текст:\n```text\n"Готовый пост"\n```'

    assert clean_llm_response(raw) == "Готовый пост"


@pytest.mark.asyncio
async def test_deepseek_rewrite_returns_cleaned_text(test_settings):
    from app.services.deepseek import DeepSeekRewriteService

    class FakeCompletions:
        async def create(self, **kwargs):
            class Message:
                content = "Вот итоговый вариант:\n@source Готовый текст t.me/source"

            class Choice:
                message = Message()

            class Response:
                choices = [Choice()]

            return Response()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    service = DeepSeekRewriteService(test_settings, client=FakeClient())

    assert await service.rewrite("original", "prompt") == "Готовый текст"
