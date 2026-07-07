import pytest


@pytest.mark.asyncio
async def test_deepseek_rewrite_disables_thinking(test_settings):
    from app.services.deepseek import DeepSeekRewriteService

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)

            class Message:
                content = "rewritten"

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

    result = await service.rewrite("original", "make it shorter")

    assert result == "rewritten"
    assert captured["model"] == "deepseek-v4-flash"
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "original" in captured["messages"][1]["content"]
    assert "make it shorter" in captured["messages"][1]["content"]
