from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class Post(TimestampMixin, Base):
    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_channel",
            "telegram_message_id",
            name="uq_posts_user_source_message",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    source_channel: Mapped[str] = mapped_column(String(255), index=True)
    target_channel: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    telegram_message_id: Mapped[int] = mapped_column(Integer)
    original_text: Mapped[str] = mapped_column(Text)
    rewritten_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publish_status: Mapped[str] = mapped_column(String(32), default="fetched")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    media_urls: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    published_media_urls: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)


class TelegramCredentials(TimestampMixin, Base):
    __tablename__ = "telegram_credentials"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phone: Mapped[str] = mapped_column(String(64))


class TelegramLoginState(TimestampMixin, Base):
    __tablename__ = "telegram_login_states"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phone: Mapped[str] = mapped_column(String(64))
    phone_code_hash: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
