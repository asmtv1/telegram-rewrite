from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import re

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    FloodWaitError,
    SessionPasswordNeededError,
    UserNotParticipantError,
)
from telethon.tl.types import MessageMediaPhoto

from app.config import Settings
from app.models import TelegramCredentials, TelegramLoginState
from app.models import utcnow


class TelegramServiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class PasswordRequired(Exception):
    pass


@dataclass(frozen=True)
class RawTelegramMessage:
    id: int
    text: str | None
    media_urls: list[str] | None = None


@dataclass(frozen=True)
class TextPost:
    id: int
    text: str
    media_urls: list[str] | None = None


@dataclass(frozen=True)
class TextPage:
    items: list[TextPost]
    next_offset_id: int | None
    has_more: bool


async def collect_text_posts(
    raw_messages: Iterable[RawTelegramMessage] | AsyncIterable[RawTelegramMessage],
    page_size: int = 10,
    raw_scan_limit: int = 100,
) -> TextPage:
    items: list[TextPost] = []
    scanned = 0
    has_more = False

    async def visit(message: RawTelegramMessage) -> bool:
        nonlocal scanned, has_more
        scanned += 1
        text = (message.text or "").strip()
        if text and len(items) < page_size:
            items.append(TextPost(id=message.id, text=text, media_urls=message.media_urls or []))
        if scanned >= raw_scan_limit or len(items) >= page_size:
            has_more = True
            return False
        return True

    if hasattr(raw_messages, "__aiter__"):
        async for message in raw_messages:  # type: ignore[union-attr]
            if not await visit(message):
                break
    else:
        for message in raw_messages:  # type: ignore[union-attr]
            if not await visit(message):
                break

    return TextPage(
        items=items,
        next_offset_id=items[-1].id if items else None,
        has_more=has_more,
    )


class TelegramService:
    def __init__(self, settings: Settings, encryption=None):
        self._settings = settings
        Path(settings.telegram_sessions_dir).mkdir(parents=True, exist_ok=True)
        Path(settings.media_dir).mkdir(parents=True, exist_ok=True)

    def _session_path(self, user_id: str) -> str:
        return str(Path(self._settings.telegram_sessions_dir) / f"{user_id}.session")

    def _client(self, user_id: str, api_id: int, api_hash: str) -> TelegramClient:
        return TelegramClient(self._session_path(user_id), api_id, api_hash)

    def _safe_media_part(self, value: str) -> str:
        cleaned = value.strip().lstrip("@") or "channel"
        return re.sub(r"[^a-zA-Z0-9_.-]+", "_", cleaned)

    def _media_url_for_path(self, path: Path) -> str:
        relative = path.relative_to(Path(self._settings.media_dir))
        return f"{self._settings.media_url_prefix.rstrip('/')}/{relative.as_posix()}"

    def _media_path_for_url(self, url: str) -> Path | None:
        prefix = self._settings.media_url_prefix.rstrip("/")
        if not url.startswith(f"{prefix}/"):
            return None
        relative = url[len(prefix) + 1 :]
        return Path(self._settings.media_dir) / relative

    async def _download_message_photos(self, client, user_id: str, source_channel: str, message) -> list[str]:
        if not isinstance(getattr(message, "media", None), MessageMediaPhoto):
            return []
        directory = (
            Path(self._settings.media_dir)
            / "posts"
            / self._safe_media_part(user_id)
            / self._safe_media_part(source_channel)
        )
        directory.mkdir(parents=True, exist_ok=True)
        downloaded = await client.download_media(message, file=str(directory / f"{message.id}"))
        if not downloaded:
            return []
        return [self._media_url_for_path(Path(downloaded))]

    async def _connect(self, client) -> None:
        await client.connect()

    async def _disconnect(self, client) -> None:
        await client.disconnect()

    async def status(self, session: AsyncSession, user_id: str) -> tuple[bool, str | None]:
        credentials = await session.get(TelegramCredentials, user_id)
        if credentials is None:
            return False, None
        client = self._app_client(user_id)
        await self._connect(client)
        try:
            connected = await client.is_user_authorized()
        finally:
            await self._disconnect(client)
        return connected, credentials.phone

    async def send_code(
        self,
        session: AsyncSession,
        user_id: str,
        phone: str,
    ) -> None:
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            sent = await client.send_code_request(phone)
        except Exception as exc:  # Telethon exposes many auth-specific subclasses.
            raise TelegramServiceError("telegram_send_code_failed", str(exc)) from exc
        finally:
            await self._disconnect(client)

        state = TelegramLoginState(
            user_id=user_id,
            phone=phone,
            phone_code_hash=sent.phone_code_hash,
            expires_at=utcnow() + timedelta(seconds=getattr(sent, "timeout", None) or 300),
        )
        await session.merge(state)
        await session.commit()

    async def sign_in(self, session: AsyncSession, user_id: str, code: str) -> None:
        state = await session.get(TelegramLoginState, user_id)
        if state is None:
            raise TelegramServiceError("telegram_login_state_missing", "Login state expired or missing")
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            await client.sign_in(
                phone=state.phone,
                code=code,
                phone_code_hash=state.phone_code_hash,
            )
        except SessionPasswordNeededError as exc:
            raise PasswordRequired() from exc
        except Exception as exc:
            raise TelegramServiceError("telegram_sign_in_failed", str(exc)) from exc
        finally:
            await self._disconnect(client)

        await self._save_credentials(session, user_id, state.phone)

    async def sign_in_password(self, session: AsyncSession, user_id: str, password: str) -> None:
        state = await session.get(TelegramLoginState, user_id)
        if state is None:
            raise TelegramServiceError("telegram_login_state_missing", "Login state expired or missing")
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            await client.sign_in(password=password)
        except Exception as exc:
            raise TelegramServiceError("telegram_password_failed", str(exc)) from exc
        finally:
            await self._disconnect(client)

        await self._save_credentials(session, user_id, state.phone)

    async def _save_credentials(
        self,
        session: AsyncSession,
        user_id: str,
        phone: str,
    ) -> None:
        await session.merge(
            TelegramCredentials(
                user_id=user_id,
                phone=phone,
            )
        )
        await session.execute(delete(TelegramLoginState).where(TelegramLoginState.user_id == user_id))
        await session.commit()

    async def logout(self, session: AsyncSession, user_id: str) -> None:
        await session.execute(delete(TelegramCredentials).where(TelegramCredentials.user_id == user_id))
        await session.execute(delete(TelegramLoginState).where(TelegramLoginState.user_id == user_id))
        await session.commit()
        for path in Path(self._settings.telegram_sessions_dir).glob(f"{user_id}.session*"):
            path.unlink(missing_ok=True)

    async def fetch_text_posts(
        self,
        session: AsyncSession,
        user_id: str,
        source_channel: str,
        offset_id: int | None,
    ) -> TextPage:
        await self._require_credentials(session, user_id)
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            if not await client.is_user_authorized():
                raise TelegramServiceError("telegram_not_connected", "Telegram is not connected")
            await self._ensure_channel_member(client, source_channel)

            async def raw_stream():
                async for message in client.iter_messages(source_channel, offset_id=offset_id or 0):
                    media_urls = await self._download_message_photos(client, user_id, source_channel, message)
                    yield RawTelegramMessage(id=message.id, text=message.message, media_urls=media_urls)

            return await collect_text_posts(raw_stream())
        except TelegramServiceError:
            raise
        except (ChannelPrivateError, ChatAdminRequiredError) as exc:
            raise TelegramServiceError("telegram_channel_unavailable", str(exc)) from exc
        except FloodWaitError as exc:
            raise TelegramServiceError("telegram_flood_wait", f"Telegram rate limit: wait {exc.seconds}s") from exc
        except Exception as exc:
            raise TelegramServiceError("telegram_fetch_failed", str(exc)) from exc
        finally:
            await self._disconnect(client)

    async def _ensure_channel_member(self, client, source_channel: str) -> None:
        try:
            await client.get_permissions(source_channel, "me")
        except UserNotParticipantError as exc:
            raise TelegramServiceError(
                "telegram_not_channel_member",
                "Вы не состоите в этом Telegram-канале. Сначала подпишитесь на канал, затем повторите загрузку.",
            ) from exc

    async def _ensure_can_publish(self, client, target_channel: str) -> None:
        try:
            permissions = await client.get_permissions(target_channel, "me")
        except UserNotParticipantError as exc:
            raise TelegramServiceError(
                "telegram_publish_forbidden",
                "Вы не состоите в target-канале. Сначала добавьте аккаунт в канал и выдайте права на публикацию.",
            ) from exc
        if not (getattr(permissions, "is_chat", False) or getattr(permissions, "post_messages", False)):
            raise TelegramServiceError(
                "telegram_publish_forbidden",
                "У пользователя нет прав на публикацию в target-канал. Сначала выдайте права на публикацию.",
            )

    async def publish(
        self,
        session: AsyncSession,
        user_id: str,
        target_channel: str,
        text: str,
        media_urls: list[str] | None = None,
    ) -> None:
        await self._require_credentials(session, user_id)
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            if not await client.is_user_authorized():
                raise TelegramServiceError("telegram_not_connected", "Telegram is not connected")
            await self._ensure_can_publish(client, target_channel)
            media_paths = [
                str(path)
                for url in media_urls or []
                if (path := self._media_path_for_url(url)) is not None and path.exists()
            ]
            if media_paths:
                await client.send_file(target_channel, media_paths, caption=text)
            else:
                await client.send_message(target_channel, text)
        except TelegramServiceError:
            raise
        except ChatAdminRequiredError as exc:
            raise TelegramServiceError("telegram_publish_forbidden", str(exc)) from exc
        except FloodWaitError as exc:
            raise TelegramServiceError("telegram_flood_wait", f"Telegram rate limit: wait {exc.seconds}s") from exc
        except Exception as exc:
            raise TelegramServiceError("telegram_publish_failed", str(exc)) from exc
        finally:
            await self._disconnect(client)

    async def _require_credentials(self, session: AsyncSession, user_id: str) -> TelegramCredentials:
        credentials = await session.scalar(
            select(TelegramCredentials).where(TelegramCredentials.user_id == user_id)
        )
        if credentials is None:
            raise TelegramServiceError("telegram_not_connected", "Telegram is not connected")
        return credentials

    def _app_client(self, user_id: str) -> TelegramClient:
        if not self._settings.telegram_api_id or not self._settings.telegram_api_hash:
            raise TelegramServiceError(
                "telegram_app_credentials_missing",
                "Telegram API ID/API hash are not configured",
            )
        return self._client(
            user_id,
            self._settings.telegram_api_id,
            self._settings.telegram_api_hash,
        )


class FakeTelegramService:
    def __init__(self):
        self.connected_users: dict[str, str] = {}
        self.pages: dict[str, TextPage] = {}
        self.published: list[tuple[str, str, str]] = []

    async def status(self, session: AsyncSession, user_id: str) -> tuple[bool, str | None]:
        return user_id in self.connected_users, self.connected_users.get(user_id)

    async def send_code(self, session, user_id, phone) -> None:
        self.connected_users[user_id] = phone

    async def sign_in(self, session, user_id, code) -> None:
        return None

    async def sign_in_password(self, session, user_id, password) -> None:
        return None

    async def logout(self, session, user_id) -> None:
        self.connected_users.pop(user_id, None)

    async def fetch_text_posts(self, session, user_id, source_channel, offset_id) -> TextPage:
        return self.pages.get(source_channel, TextPage(items=[], next_offset_id=None, has_more=False))

    async def publish(self, session, user_id, target_channel, text, media_urls=None) -> None:
        self.published.append((user_id, target_channel, text, media_urls or []))
