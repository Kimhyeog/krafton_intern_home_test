from datetime import datetime, timedelta, timezone
from uuid import uuid4
import bcrypt
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db import db
from app.config import get_settings

settings = get_settings()
security = HTTPBearer()


# ===== 비밀번호 =====

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ===== JWT Access Token =====

def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> int:
    """JWT를 디코딩하여 user_id 반환. 실패 시 HTTPException."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload["sub"])
        return user_id
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 인증 토큰입니다.",
        )


# ===== Refresh Token (DB 저장, 일회용) =====

async def create_refresh_token(user_id: int) -> str:
    """새 Refresh Token을 생성하고 DB에 저장."""
    token = str(uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    await db.refreshtoken.create(data={
        "token": token,
        "userId": user_id,
        "expiresAt": expires_at,
    })
    return token

async def rotate_refresh_token(old_token: str) -> tuple[str, str]:
    """
    Refresh Token Rotation:
    1. old_token을 DB에서 찾아 삭제 (일회용)
    2. 새 Access Token + 새 Refresh Token 발급
    탈취 감지: 이미 삭제된 토큰으로 요청 시 해당 유저의 모든 RT 무효화
    """
    rt = await db.refreshtoken.find_unique(where={"token": old_token})

    if not rt:
        # 이미 사용된 토큰 → 탈취 감지
        # old_token의 userId를 알 수 없으므로, 401만 반환
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token_reuse_detected",
        )

    # 만료 확인
    if rt.expiresAt.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        await db.refreshtoken.delete(where={"id": rt.id})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token이 만료되었습니다.",
        )

    # 일회용 소멸: 기존 RT 삭제
    await db.refreshtoken.delete(where={"id": rt.id})

    # 새 토큰 발급
    new_access = create_access_token(rt.userId)
    new_refresh = await create_refresh_token(rt.userId)
    return new_access, new_refresh

async def revoke_all_tokens(user_id: int):
    """해당 유저의 모든 Refresh Token 무효화 (탈취 감지 또는 로그아웃)."""
    await db.refreshtoken.delete_many(where={"userId": user_id})

async def revoke_token(token: str):
    """특정 Refresh Token 무효화 (로그아웃)."""
    rt = await db.refreshtoken.find_unique(where={"token": token})
    if rt:
        await db.refreshtoken.delete(where={"id": rt.id})


# ===== FastAPI Depends =====

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Bearer Token에서 현재 사용자를 추출하는 FastAPI 의존성."""
    user_id = decode_access_token(credentials.credentials)
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자를 찾을 수 없습니다.",
        )
    return user
