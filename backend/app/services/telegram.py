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
    AuthKeyError,
    ChannelInvalidError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    SessionPasswordNeededError,
    UnauthorizedError,
    UserNotParticipantError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import MessageMediaPhoto
from telethon.utils import get_peer_id

from app.config import Settings
from app.models import TelegramCredentials, TelegramLoginState
from app.models import utcnow


TELEGRAM_TEXT_LIMIT = 4096
TELEGRAM_CAPTION_LIMIT = 1024

_TME_C_RE = re.compile(r"(?:https?://)?t\.me/c/(\d+)(?:/\d+)?/?$", re.IGNORECASE)
_TME_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_]+)(?:/\d+)?/?$", re.IGNORECASE)


class TelegramServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class PasswordRequired(Exception):
    pass


def normalize_channel(raw: str) -> str | int:
    value = raw.strip()
    match = _TME_C_RE.match(value)
    if match:
        return int(f"-100{match.group(1)}")
    match = _TME_RE.match(value)
    if match:
        value = match.group(1)
    value = value.lstrip("@").strip()
    if not value:
        raise TelegramServiceError("telegram_channel_not_found", "Укажите канал", status_code=404)
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def canonical_channel_id(raw: str) -> str:
    return str(normalize_channel(raw))


def _fit_caption(text: str) -> str:
    if len(text) <= TELEGRAM_CAPTION_LIMIT:
        return text
    head = text[:TELEGRAM_CAPTION_LIMIT]
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind("\n"))
    if cut > TELEGRAM_CAPTION_LIMIT // 2:
        return head[: cut + 1].strip()
    return head.rstrip()


def _split_text(text: str) -> list[str]:
    return [text[i : i + TELEGRAM_TEXT_LIMIT] for i in range(0, len(text), TELEGRAM_TEXT_LIMIT)]


def build_publish_parts(text: str, has_media: bool) -> list[tuple[str, str]]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if has_media:
        return [("media", _fit_caption(cleaned))]
    return [("text", chunk) for chunk in _split_text(cleaned)]


def map_telegram_error(exc: Exception, channel: str | None = None) -> TelegramServiceError:
    where = f" ({channel})" if channel else ""
    if isinstance(exc, FloodWaitError):
        return TelegramServiceError(
            "telegram_flood_wait",
            f"Telegram просит подождать {exc.seconds} сек и повторить запрос",
            status_code=429,
        )
    if isinstance(exc, (UsernameNotOccupiedError, UsernameInvalidError, ChannelInvalidError, ValueError)):
        return TelegramServiceError(
            "telegram_channel_not_found",
            f"Канал не найден{where}. Проверьте имя или ссылку",
            status_code=404,
        )
    if isinstance(exc, (ChannelPrivateError, UserNotParticipantError)):
        return TelegramServiceError(
            "telegram_channel_access_denied",
            f"Нет доступа к каналу{where}: аккаунт в нём не состоит",
            status_code=403,
        )
    if isinstance(exc, (ChatWriteForbiddenError, ChatAdminRequiredError)):
        return TelegramServiceError(
            "telegram_publish_forbidden",
            f"Нет прав на публикацию в канале{where}",
            status_code=403,
        )
    if isinstance(exc, (AuthKeyError, UnauthorizedError)):
        return TelegramServiceError(
            "telegram_not_connected",
            "Telegram-сессия не создана или недействительна. Подключите Telegram-аккаунт заново.",
            status_code=503,
        )
    return TelegramServiceError(
        "telegram_unexpected_error",
        f"Неожиданная ошибка Telegram ({type(exc).__name__}). Подробности в логах сервера",
        status_code=502,
    )


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
    source_channel_id: str | None = None


@dataclass(frozen=True)
class PublishResult:
    message_id: int | None
    url: str | None


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


def _first_message_id(sent) -> int | None:
    if isinstance(sent, (list, tuple)):
        for item in sent:
            message_id = getattr(item, "id", None)
            if message_id is not None:
                return int(message_id)
        return None
    message_id = getattr(sent, "id", None)
    return int(message_id) if message_id is not None else None


def _combine_grouped_messages(messages: list[RawTelegramMessage]) -> RawTelegramMessage:
    text_message = next((message for message in messages if (message.text or "").strip()), messages[-1])
    media_urls: list[str] = []
    seen_media_urls: set[str] = set()
    for message in sorted(messages, key=lambda item: item.id):
        for url in message.media_urls or []:
            if url in seen_media_urls:
                continue
            seen_media_urls.add(url)
            media_urls.append(url)
    return RawTelegramMessage(id=text_message.id, text=text_message.text, media_urls=media_urls)


def build_message_url(raw_channel: str, normalized_channel: str | int, message_id: int | None) -> str | None:
    if message_id is None:
        return None
    c_match = _TME_C_RE.match(raw_channel.strip())
    if c_match:
        return f"https://t.me/c/{c_match.group(1)}/{message_id}"
    if isinstance(normalized_channel, int):
        value = str(normalized_channel)
        if value.startswith("-100"):
            return f"https://t.me/c/{value[4:]}/{message_id}"
        return None
    match = _TME_RE.match(raw_channel.strip())
    slug = match.group(1) if match else raw_channel.strip().lstrip("@")
    if not slug or re.fullmatch(r"-?\d+", slug):
        return None
    return f"https://t.me/{slug}/{message_id}"


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

    def _existing_message_photo(self, directory: Path, message_id: int) -> Path | None:
        exact_path = directory / str(message_id)
        if exact_path.is_file() and exact_path.stat().st_size > 0:
            return exact_path
        for path in sorted(directory.glob(f"{message_id}.*")):
            if path.is_file() and path.stat().st_size > 0:
                return path
        return None

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
        existing = self._existing_message_photo(directory, message.id)
        if existing is not None:
            return [self._media_url_for_path(existing)]
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
            normalized_source_channel = normalize_channel(source_channel)
            await self._ensure_channel_member(client, normalized_source_channel)
            if hasattr(client, "get_entity"):
                source_entity = await client.get_entity(normalized_source_channel)
                source_channel_id = str(get_peer_id(source_entity))
            else:
                source_entity = normalized_source_channel
                source_channel_id = canonical_channel_id(source_channel)

            async def raw_stream():
                grouped_id = None
                grouped_messages: list[RawTelegramMessage] = []

                async def flush_grouped():
                    nonlocal grouped_id, grouped_messages
                    if not grouped_messages:
                        return None
                    raw_message = _combine_grouped_messages(grouped_messages)
                    grouped_id = None
                    grouped_messages = []
                    return raw_message

                async for message in client.iter_messages(source_entity, offset_id=offset_id or 0):
                    media_urls = await self._download_message_photos(client, user_id, source_channel_id, message)
                    message_grouped_id = getattr(message, "grouped_id", None)
                    raw_message = RawTelegramMessage(id=message.id, text=message.message, media_urls=media_urls)
                    if message_grouped_id is not None:
                        if grouped_id is None:
                            grouped_id = message_grouped_id
                        if grouped_id == message_grouped_id:
                            grouped_messages.append(raw_message)
                            continue
                        combined = await flush_grouped()
                        if combined is not None:
                            yield combined
                        grouped_id = message_grouped_id
                        grouped_messages.append(raw_message)
                        continue
                    combined = await flush_grouped()
                    if combined is not None:
                        yield combined
                    yield raw_message

                combined = await flush_grouped()
                if combined is not None:
                    yield combined

            page = await collect_text_posts(raw_stream())
            return TextPage(
                items=page.items,
                next_offset_id=page.next_offset_id,
                has_more=page.has_more,
                source_channel_id=source_channel_id,
            )
        except TelegramServiceError:
            raise
        except Exception as exc:
            raise map_telegram_error(exc, source_channel) from exc
        finally:
            await self._disconnect(client)

    async def _ensure_channel_member(self, client, source_channel: str | int) -> None:
        try:
            await client.get_permissions(source_channel, "me")
        except UserNotParticipantError as exc:
            raise TelegramServiceError(
                "telegram_not_channel_member",
                "Вы не состоите в этом Telegram-канале. Сначала подпишитесь на канал, затем повторите загрузку.",
                status_code=403,
            ) from exc

    async def _ensure_can_publish(self, client, target_channel: str) -> None:
        normalized_target_channel = normalize_channel(target_channel)
        try:
            permissions = await client.get_permissions(normalized_target_channel, "me")
        except UserNotParticipantError as exc:
            raise TelegramServiceError(
                "telegram_publish_forbidden",
                "Вы не состоите в target-канале. Сначала добавьте аккаунт в канал и выдайте права на публикацию.",
                status_code=403,
            ) from exc
        if not (getattr(permissions, "is_chat", False) or getattr(permissions, "post_messages", False)):
            raise TelegramServiceError(
                "telegram_publish_forbidden",
                "У пользователя нет прав на публикацию в target-канал. Сначала выдайте права на публикацию.",
                status_code=403,
            )

    async def publish(
        self,
        session: AsyncSession,
        user_id: str,
        target_channel: str,
        text: str,
        media_urls: list[str] | None = None,
    ) -> PublishResult:
        await self._require_credentials(session, user_id)
        client = self._app_client(user_id)
        try:
            await self._connect(client)
            if not await client.is_user_authorized():
                raise TelegramServiceError("telegram_not_connected", "Telegram is not connected", status_code=503)
            await self._ensure_can_publish(client, target_channel)
            media_paths = [
                str(path)
                for url in media_urls or []
                if (path := self._media_path_for_url(url)) is not None and path.exists()
            ]
            normalized_target_channel = normalize_channel(target_channel)
            parts = build_publish_parts(text, has_media=bool(media_paths))
            if not parts:
                raise TelegramServiceError("telegram_empty_message", "Текст публикации пуст", status_code=422)
            published_message_id = None
            for kind, chunk in parts:
                if kind == "media":
                    sent = await client.send_file(normalized_target_channel, media_paths, caption=chunk, parse_mode=None)
                else:
                    sent = await client.send_message(normalized_target_channel, chunk, parse_mode=None)
                if published_message_id is None:
                    published_message_id = _first_message_id(sent)
            return PublishResult(
                message_id=published_message_id,
                url=build_message_url(target_channel, normalized_target_channel, published_message_id),
            )
        except TelegramServiceError:
            raise
        except Exception as exc:
            raise map_telegram_error(exc, target_channel) from exc
        finally:
            await self._disconnect(client)

    async def _require_credentials(self, session: AsyncSession, user_id: str) -> TelegramCredentials:
        credentials = await session.scalar(
            select(TelegramCredentials).where(TelegramCredentials.user_id == user_id)
        )
        if credentials is None:
            raise TelegramServiceError("telegram_not_connected", "Telegram is not connected", status_code=503)
        return credentials

    def _app_client(self, user_id: str) -> TelegramClient:
        if not self._settings.telegram_api_id or not self._settings.telegram_api_hash:
            raise TelegramServiceError(
                "telegram_app_credentials_missing",
                "Telegram API ID/API hash are not configured",
                status_code=503,
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

    async def publish(self, session, user_id, target_channel, text, media_urls=None) -> PublishResult:
        self.published.append((user_id, target_channel, text, media_urls or []))
        return PublishResult(message_id=None, url=None)
