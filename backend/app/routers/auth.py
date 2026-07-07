from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.dependencies import current_user_id
from app.schemas import CurrentUserResponse, LoginRequest
from app.security import verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, payload: LoginRequest):
    users = request.app.state.settings.parsed_users()
    if not verify_password(payload.username, payload.password, users):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    request.session["user_id"] = payload.username
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/me", response_model=CurrentUserResponse)
async def me(user_id: str = Depends(current_user_id)):
    return CurrentUserResponse(user_id=user_id)
