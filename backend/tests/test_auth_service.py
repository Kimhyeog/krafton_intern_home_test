"""
인증 서비스 단위 테스트

테스트 대상: backend/app/services/auth.py
- 비밀번호 해싱/검증 (bcrypt)
- JWT Access Token 생성/디코딩
- Refresh Token 로테이션/탈취 감지

유형: Unit Test — 순수 함수 직접 테스트 + DB 의존 함수는 DB만 mock
전략: 디트로이트파 (Classicist)
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

pytestmark = pytest.mark.unit


# ===== 비밀번호 해싱 (순수 함수, mock 불필요) =====

class TestPasswordHashing:
    """bcrypt 기반 비밀번호 해싱/검증 — 외부 의존성 없는 순수 Unit Test"""

    def test_hash_password_returns_bcrypt_hash(self):
        """해싱 결과가 bcrypt 형식($2b$...)"""
        from app.services.auth import hash_password
        result = hash_password("mypassword123")
        assert result.startswith("$2b$")

    def test_hash_password_different_salt_each_time(self):
        """같은 입력이라도 매번 다른 해시 (salt 랜덤)"""
        from app.services.auth import hash_password
        h1 = hash_password("samepassword")
        h2 = hash_password("samepassword")
        assert h1 != h2

    def test_verify_password_correct(self):
        """올바른 비밀번호 → True"""
        from app.services.auth import hash_password, verify_password
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_verify_password_incorrect(self):
        """틀린 비밀번호 → False"""
        from app.services.auth import hash_password, verify_password
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_case_sensitive(self):
        """대소문자 구별"""
        from app.services.auth import hash_password, verify_password
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False
        assert verify_password("PASSWORD", hashed) is False
        assert verify_password("Password", hashed) is True

    def test_hash_password_unicode(self):
        """한글 비밀번호도 정상 처리"""
        from app.services.auth import hash_password, verify_password
        hashed = hash_password("비밀번호123")
        assert verify_password("비밀번호123", hashed) is True
        assert verify_password("비밀번호124", hashed) is False


# ===== JWT Access Token (순수 함수 + Settings 의존) =====

class TestAccessToken:
    """JWT 생성/디코딩 — Settings만 사용, DB 불필요"""

    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
        from app.config import get_settings
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_create_access_token_returns_string(self):
        """JWT 토큰은 문자열"""
        from app.services.auth import create_access_token
        token = create_access_token(user_id=42)
        assert isinstance(token, str)
        assert len(token) > 20

    def test_decode_access_token_roundtrip(self):
        """생성한 토큰을 디코딩하면 동일한 user_id"""
        from app.services.auth import create_access_token, decode_access_token
        token = create_access_token(user_id=99)
        user_id = decode_access_token(token)
        assert user_id == 99

    def test_decode_access_token_invalid_raises_401(self):
        """유효하지 않은 토큰 → HTTPException 401"""
        from app.services.auth import decode_access_token
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("invalid.jwt.token")
        assert exc_info.value.status_code == 401

    def test_decode_access_token_wrong_secret_raises_401(self):
        """다른 시크릿으로 서명된 토큰 → 401"""
        from jose import jwt
        fake_token = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret-key",
            algorithm="HS256",
        )
        from app.services.auth import decode_access_token
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(fake_token)
        assert exc_info.value.status_code == 401

    def test_decode_access_token_expired_raises_401(self):
        """만료된 토큰 → 401"""
        from jose import jwt
        from app.config import get_settings
        settings = get_settings()
        expired_token = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        from app.services.auth import decode_access_token
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(expired_token)
        assert exc_info.value.status_code == 401

    def test_decode_access_token_missing_sub_raises_401(self):
        """sub 클레임 없는 토큰 → 401"""
        from jose import jwt
        from app.config import get_settings
        settings = get_settings()
        token = jwt.encode(
            {"exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        from app.services.auth import decode_access_token
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401


# ===== Refresh Token (DB 의존 → mock) =====

class TestRefreshToken:
    """Refresh Token 로테이션/탈취 감지 — DB만 mock"""

    @pytest.fixture(autouse=True)
    def setup_settings(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
        from app.config import get_settings
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    async def test_create_refresh_token_returns_uuid_string(self):
        """RT 생성 결과는 UUID 형식 문자열"""
        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.create = AsyncMock()
            from app.services.auth import create_refresh_token
            token = await create_refresh_token(user_id=1)
            assert isinstance(token, str)
            assert len(token) == 36  # UUID4 길이

    async def test_create_refresh_token_saves_to_db(self):
        """RT 생성 시 DB에 저장"""
        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.create = AsyncMock()
            from app.services.auth import create_refresh_token
            await create_refresh_token(user_id=5)
            mock_db.refreshtoken.create.assert_called_once()
            call_data = mock_db.refreshtoken.create.call_args[1]["data"]
            assert call_data["userId"] == 5

    async def test_rotate_refresh_token_issues_new_pair(self):
        """유효한 RT로 로테이션 → 새 AT + RT 반환"""
        mock_rt = MagicMock()
        mock_rt.id = 1
        mock_rt.userId = 42
        mock_rt.expiresAt = datetime.now(timezone.utc) + timedelta(days=7)

        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
            mock_db.refreshtoken.delete = AsyncMock()
            mock_db.refreshtoken.create = AsyncMock()

            from app.services.auth import rotate_refresh_token
            new_access, new_refresh = await rotate_refresh_token("old-token")

            assert isinstance(new_access, str)
            assert isinstance(new_refresh, str)
            assert len(new_access) > 20  # JWT
            assert len(new_refresh) == 36  # UUID

    async def test_rotate_refresh_token_deletes_old(self):
        """로테이션 시 기존 RT 삭제 (일회용)"""
        mock_rt = MagicMock()
        mock_rt.id = 10
        mock_rt.userId = 1
        mock_rt.expiresAt = datetime.now(timezone.utc) + timedelta(days=7)

        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
            mock_db.refreshtoken.delete = AsyncMock()
            mock_db.refreshtoken.create = AsyncMock()

            from app.services.auth import rotate_refresh_token
            await rotate_refresh_token("old-token")

            mock_db.refreshtoken.delete.assert_called_with(where={"id": 10})

    async def test_rotate_reused_token_raises_401(self):
        """이미 사용된(삭제된) RT로 요청 → 탈취 감지, 401"""
        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=None)

            from app.services.auth import rotate_refresh_token
            with pytest.raises(HTTPException) as exc_info:
                await rotate_refresh_token("reused-token")
            assert exc_info.value.status_code == 401
            assert "token_reuse_detected" in exc_info.value.detail

    async def test_rotate_expired_token_raises_401(self):
        """만료된 RT → 401"""
        mock_rt = MagicMock()
        mock_rt.id = 1
        mock_rt.userId = 1
        mock_rt.expiresAt = datetime.now(timezone.utc) - timedelta(days=1)

        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
            mock_db.refreshtoken.delete = AsyncMock()

            from app.services.auth import rotate_refresh_token
            with pytest.raises(HTTPException) as exc_info:
                await rotate_refresh_token("expired-token")
            assert exc_info.value.status_code == 401

    async def test_revoke_token_deletes_from_db(self):
        """RT 폐기 → DB에서 삭제"""
        mock_rt = MagicMock()
        mock_rt.id = 7

        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
            mock_db.refreshtoken.delete = AsyncMock()

            from app.services.auth import revoke_token
            await revoke_token("some-token")
            mock_db.refreshtoken.delete.assert_called_once()

    async def test_revoke_token_nonexistent_is_noop(self):
        """존재하지 않는 RT 폐기 → 에러 없이 무시"""
        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.find_unique = AsyncMock(return_value=None)
            mock_db.refreshtoken.delete = AsyncMock()

            from app.services.auth import revoke_token
            await revoke_token("nonexistent-token")
            mock_db.refreshtoken.delete.assert_not_called()

    async def test_revoke_all_tokens(self):
        """특정 유저의 모든 RT 삭제"""
        with patch("app.services.auth.db") as mock_db:
            mock_db.refreshtoken.delete_many = AsyncMock()

            from app.services.auth import revoke_all_tokens
            await revoke_all_tokens(user_id=3)
            mock_db.refreshtoken.delete_many.assert_called_once_with(where={"userId": 3})
