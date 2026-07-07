import pytest


@pytest.mark.asyncio
async def test_deepseek_rewrite_requires_api_key(test_settings):
    from app.services.deepseek import DeepSeekRewriteService, RewriteServiceError

    settings = test_settings.model_copy(update={"deepseek_api_key": ""})
    service = DeepSeekRewriteService(settings, client=object())

    with pytest.raises(RewriteServiceError) as exc:
        await service.rewrite("original", "prompt")

    assert exc.value.code == "deepseek_api_key_missing"
    assert "DEEPSEEK_API_KEY" in exc.value.message
