from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.services.deepseek import llm_configured, resolve_llm_config

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health(request: Request, session: AsyncSession = Depends(get_db)):
    settings = request.app.state.settings
    await session.execute(text("select 1"))
    sessions_dir = Path(settings.telegram_sessions_dir)
    llm = resolve_llm_config(settings)
    return {
        "status": "ok",
        "db": "ok",
        "telegram": {
            "api_configured": bool(settings.telegram_api_id and settings.telegram_api_hash),
            "sessions_dir": "ok" if sessions_dir.is_dir() else "missing",
            "session_files": len(list(sessions_dir.glob("*.session*"))) if sessions_dir.is_dir() else 0,
        },
        "llm": {
            "provider": llm.provider,
            "model": llm.model,
            "base_url": llm.base_url,
            "configured": llm_configured(settings),
        },
    }
