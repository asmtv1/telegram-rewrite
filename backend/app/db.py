from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base


def make_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_async_engine(database_url, connect_args=connect_args, future=True)


def make_session_maker(engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_schema(engine) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"] for column in inspect(sync_connection).get_columns("posts")
            }
        )
        if "published_at" not in columns:
            await connection.execute(text("ALTER TABLE posts ADD COLUMN published_at TIMESTAMP"))
        if "media_urls" not in columns:
            await connection.execute(text("ALTER TABLE posts ADD COLUMN media_urls JSON DEFAULT '[]' NOT NULL"))
        if "published_media_urls" not in columns:
            await connection.execute(text("ALTER TABLE posts ADD COLUMN published_media_urls JSON"))


def get_session_maker(app) -> async_sessionmaker[AsyncSession]:
    return app.state.session_maker


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_maker() as session:
        yield session
