from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.db import create_schema, make_engine, make_session_maker
from app.routers import auth, health, posts, telegram
from app.security import EncryptionService
from app.services.deepseek import DeepSeekRewriteService
from app.services.telegram import TelegramService


def create_app(
    settings: Optional[Settings] = None,
    telegram_service=None,
    rewrite_service=None,
) -> FastAPI:
    app_settings = settings or get_settings()
    engine = make_engine(app_settings.database_url)
    session_maker = make_session_maker(engine)
    encryption = EncryptionService(app_settings.app_encryption_key)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await create_schema(engine)
        yield
        await engine.dispose()

    app = FastAPI(title="testovoe3 Telegram Rewrite App", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.session_secret,
        same_site="lax",
        https_only=app_settings.session_cookie_secure,
    )
    app.state.settings = app_settings
    app.state.session_maker = session_maker
    app.state.telegram_service = telegram_service or TelegramService(app_settings, encryption)
    app.state.rewrite_service = rewrite_service or DeepSeekRewriteService(app_settings)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(telegram.router)
    app.include_router(posts.router)
    app.mount(
        app_settings.media_url_prefix,
        StaticFiles(directory=app_settings.media_dir),
        name="media",
    )
    return app


app = create_app()
