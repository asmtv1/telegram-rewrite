from __future__ import annotations

from pathlib import Path
import re
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import current_user_id
from app.models import Post, utcnow
from app.schemas import MediaUploadResponse, PostResponse, PostsHistoryResponse, PostsPageResponse, PublishRequest, RewriteRequest
from app.services.telegram import TelegramServiceError

router = APIRouter(prefix="/api/posts", tags=["posts"])


async def _get_owned_post(session: AsyncSession, user_id: str, post_id: int) -> Post:
    post = await session.scalar(select(Post).where(Post.id == post_id, Post.user_id == user_id))
    if post is None:
        raise HTTPException(status_code=404, detail="post_not_found")
    return post


def _safe_media_part(value: str) -> str:
    cleaned = value.strip().lstrip("@") or "value"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", cleaned)


def _media_url_for_path(request: Request, path: Path) -> str:
    settings = request.app.state.settings
    relative = path.relative_to(Path(settings.media_dir))
    return f"{settings.media_url_prefix.rstrip('/')}/{relative.as_posix()}"


def _uploaded_media_prefix(request: Request, user_id: str) -> str:
    settings = request.app.state.settings
    return f"{settings.media_url_prefix.rstrip('/')}/uploads/{_safe_media_part(user_id)}/"


def _publish_media_urls(request: Request, post: Post, user_id: str, requested_urls: list[str] | None) -> list[str]:
    if requested_urls is None:
        return post.media_urls

    original_urls = set(post.media_urls)
    uploaded_prefix = _uploaded_media_prefix(request, user_id)
    invalid_urls = [
        url
        for url in requested_urls
        if url not in original_urls and not url.startswith(uploaded_prefix)
    ]
    if invalid_urls:
        raise HTTPException(status_code=422, detail="invalid_media_url")
    return requested_urls


@router.get("/history", response_model=PostsHistoryResponse)
async def history_posts(
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    result = await session.scalars(
        select(Post)
        .where(
            Post.user_id == user_id,
            or_(
                Post.rewritten_text.is_not(None),
                Post.publish_status.in_(["rewritten", "published", "error"]),
            ),
        )
        .order_by(desc(Post.updated_at))
    )
    return PostsHistoryResponse(items=[PostResponse.model_validate(post) for post in result.all()])


@router.get("", response_model=PostsPageResponse)
async def list_posts(
    request: Request,
    source_channel: str = Query(min_length=1),
    target_channel: Optional[str] = Query(default=None, min_length=1),
    offset_id: Optional[int] = None,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        page = await request.app.state.telegram_service.fetch_text_posts(
            session,
            user_id,
            source_channel,
            offset_id,
        )
    except TelegramServiceError as exc:
        raise HTTPException(status_code=400, detail=exc.message) from exc

    items: list[Post] = []
    for item in page.items:
        existing = await session.scalar(
            select(Post).where(
                Post.user_id == user_id,
                Post.source_channel == source_channel,
                Post.telegram_message_id == item.id,
            )
        )
        if existing is None:
            existing = Post(
                user_id=user_id,
                source_channel=source_channel,
                target_channel=target_channel,
                telegram_message_id=item.id,
                original_text=item.text,
                media_urls=item.media_urls or [],
                publish_status="fetched",
            )
            session.add(existing)
        else:
            existing.target_channel = target_channel
            existing.original_text = item.text
            existing.media_urls = item.media_urls or []
        items.append(existing)

    await session.commit()
    for post in items:
        await session.refresh(post)

    return PostsPageResponse(
        items=[PostResponse.model_validate(post) for post in items],
        next_offset_id=page.next_offset_id,
        has_more=page.has_more,
        message=None if items else "No text posts found",
    )


@router.post("/{post_id}/rewrite", response_model=PostResponse)
async def rewrite_post(
    post_id: int,
    payload: RewriteRequest,
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    post = await _get_owned_post(session, user_id, post_id)
    try:
        post.rewritten_text = await request.app.state.rewrite_service.rewrite(
            post.original_text,
            payload.prompt,
        )
        post.publish_status = "rewritten"
        post.error_message = None
    except Exception as exc:
        post.publish_status = "error"
        post.error_message = str(exc)
    await session.commit()
    await session.refresh(post)
    return PostResponse.model_validate(post)


@router.post("/{post_id}/media", response_model=MediaUploadResponse)
async def upload_post_media(
    post_id: int,
    request: Request,
    files: list[UploadFile] = File(...),
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    await _get_owned_post(session, user_id, post_id)
    if not files:
        raise HTTPException(status_code=422, detail="files_required")
    if len(files) > 2:
        raise HTTPException(status_code=422, detail="too_many_files")

    settings = request.app.state.settings
    directory = Path(settings.media_dir) / "uploads" / _safe_media_part(user_id) / str(post_id)
    directory.mkdir(parents=True, exist_ok=True)

    media_urls: list[str] = []
    for upload in files:
        if not (upload.content_type or "").startswith("image/"):
            raise HTTPException(status_code=422, detail="image_files_only")
        suffix = Path(upload.filename or "").suffix.lower()[:16] or ".jpg"
        path = directory / f"{uuid4().hex}{suffix}"
        path.write_bytes(await upload.read())
        media_urls.append(_media_url_for_path(request, path))

    return MediaUploadResponse(media_urls=media_urls)


@router.post("/{post_id}/publish", response_model=PostResponse)
async def publish_post(
    post_id: int,
    payload: PublishRequest,
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    post = await _get_owned_post(session, user_id, post_id)
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="text_required")
    post.target_channel = payload.target_channel
    post.rewritten_text = text
    media_urls = _publish_media_urls(request, post, user_id, payload.media_urls)
    try:
        await request.app.state.telegram_service.publish(
            session,
            user_id,
            payload.target_channel,
            text,
            media_urls,
        )
        post.publish_status = "published"
        post.published_media_urls = media_urls
        post.published_at = utcnow()
        post.error_message = None
    except TelegramServiceError as exc:
        post.publish_status = "error"
        post.error_message = exc.message
    await session.commit()
    await session.refresh(post)
    return PostResponse.model_validate(post)
