from openai import AsyncOpenAI

from app.config import Settings


class RewriteServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class DeepSeekRewriteService:
    def __init__(self, settings: Settings, client=None):
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

    async def rewrite(self, original_text: str, prompt: str) -> str:
        if not self._settings.deepseek_api_key:
            raise RewriteServiceError(
                "deepseek_api_key_missing",
                "DEEPSEEK_API_KEY не настроен. Добавьте ключ DeepSeek в .env и перезапустите backend.",
            )
        response = await self._client.chat.completions.create(
            model=self._settings.deepseek_model,
            messages=[
                {
                    "role": "system",
                    "content": "Ты аккуратный редактор Telegram-постов. Сохраняй смысл и возвращай только готовый текст.",
                },
                {
                    "role": "user",
                    "content": f"Инструкция:\n{prompt}\n\nИсходный текст:\n{original_text}",
                },
            ],
            extra_body={"thinking": {"type": "disabled"}},
        )
        return response.choices[0].message.content or ""


class FakeRewriteService:
    def __init__(self, result: str):
        self.result = result

    async def rewrite(self, original_text: str, prompt: str) -> str:
        return self.result
