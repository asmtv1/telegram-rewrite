from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://testovoe3:testovoe3@postgres:5432/testovoe3"
    session_secret: str
    app_users: str = "user1:12345,user2:2407041"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 45.0
    app_encryption_key: str
    telegram_api_id: int = 0
    telegram_api_hash: str = ""
    telegram_sessions_dir: str = "/app/sessions"
    media_dir: str = "/app/media"
    media_url_prefix: str = "/media"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def parsed_users(self) -> dict[str, str]:
        users: dict[str, str] = {}
        for item in self.app_users.split(","):
            if not item.strip():
                continue
            username, separator, password = item.partition(":")
            if not separator or not username or not password:
                raise ValueError("APP_USERS must contain username:password pairs")
            users[username] = password
        return users


@lru_cache
def get_settings() -> Settings:
    return Settings()
