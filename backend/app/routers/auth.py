from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from app.db import db
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    rotate_refresh_token,
    revoke_token,
    get_current_user,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ===== Request / Response Models =====

class SignupRequest(BaseModel):
    email: str
    username: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class RefreshRequest(BaseModel):
    refresh_token: str

class LogoutRequest(BaseModel):
    refresh_token: str

class UserResponse(BaseModel):
    id: int
    email: str
    username: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ===== Endpoints =====

@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest):
    # 이메일 중복 확인
    existing = await db.user.find_unique(where={"email": request.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일입니다.",
        )
    # 유저네임 중복 확인
    existing = await db.user.find_unique(where={"username": request.username})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 유저네임입니다.",
        )

    hashed = hash_password(request.password)
    user = await db.user.create(data={
        "email": request.email,
        "username": request.username,
        "password": hashed,
    })
    return UserResponse(id=user.id, email=user.email, username=user.username)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    user = await db.user.find_unique(where={"email": request.email})
    if not user or not verify_password(request.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다.",
        )

    access_token = create_access_token(user.id)
    refresh_token = await create_refresh_token(user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    new_access, new_refresh = await rotate_refresh_token(request.refresh_token)
    return TokenResponse(access_token=new_access, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(request: LogoutRequest):
    await revoke_token(request.refresh_token)
    return {"message": "로그아웃되었습니다."}


@router.get("/me", response_model=UserResponse)
async def me(current_user=Depends(get_current_user)):
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
    )
