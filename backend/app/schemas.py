from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class CurrentUserResponse(BaseModel):
    user_id: str


class TelegramSendCodeRequest(BaseModel):
    phone: str


class TelegramSignInRequest(BaseModel):
    code: str


class TelegramPasswordRequest(BaseModel):
    password: str


class TelegramStatusResponse(BaseModel):
    connected: bool
    phone: Optional[str] = None
    needs_credentials: bool


class PostResponse(BaseModel):
    id: int
    source_channel: str
    source_channel_id: Optional[str] = None
    target_channel: Optional[str] = None
    telegram_message_id: int
    original_text: str
    rewritten_text: Optional[str] = None
    publish_status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    published_at: Optional[datetime] = None
    published_message_id: Optional[int] = None
    published_url: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)
    published_media_urls: Optional[List[str]] = None

    model_config = {"from_attributes": True}


class PostsPageResponse(BaseModel):
    items: List[PostResponse]
    next_offset_id: Optional[int]
    has_more: bool
    message: Optional[str] = None


class PostsHistoryResponse(BaseModel):
    items: List[PostResponse]


class MediaUploadResponse(BaseModel):
    media_urls: List[str] = Field(default_factory=list)


class RewriteRequest(BaseModel):
    prompt: str = Field(min_length=1)


class PublishRequest(BaseModel):
    target_channel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    media_urls: Optional[List[str]] = None
