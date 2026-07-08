from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.dependencies import current_user_id
from app.schemas import (
    TelegramPasswordRequest,
    TelegramSendCodeRequest,
    TelegramSignInRequest,
    TelegramStatusResponse,
)
from app.services.telegram import PasswordRequired, TelegramServiceError

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


@router.get("/status", response_model=TelegramStatusResponse)
async def status(
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    connected, phone = await request.app.state.telegram_service.status(session, user_id)
    return TelegramStatusResponse(
        connected=connected,
        phone=phone,
        needs_credentials=not connected,
    )


@router.post("/send-code")
async def send_code(
    payload: TelegramSendCodeRequest,
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        await request.app.state.telegram_service.send_code(
            session,
            user_id,
            payload.phone,
        )
    except TelegramServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"ok": True}


@router.post("/sign-in")
async def sign_in(
    payload: TelegramSignInRequest,
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        await request.app.state.telegram_service.sign_in(session, user_id, payload.code)
    except PasswordRequired:
        return {"password_required": True}
    except TelegramServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"ok": True, "password_required": False}


@router.post("/password")
async def password(
    payload: TelegramPasswordRequest,
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    try:
        await request.app.state.telegram_service.sign_in_password(session, user_id, payload.password)
    except TelegramServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"ok": True}


@router.post("/logout")
async def logout(
    request: Request,
    user_id: str = Depends(current_user_id),
    session: AsyncSession = Depends(get_db),
):
    await request.app.state.telegram_service.logout(session, user_id)
    return {"ok": True}
