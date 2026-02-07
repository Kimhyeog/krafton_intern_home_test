"""
인증 API 엔드포인트 통합 테스트

테스트 대상: backend/app/routers/auth.py
- 회원가입 (POST /api/auth/signup)
- 로그인 (POST /api/auth/login)
- 토큰 갱신 (POST /api/auth/refresh)
- 로그아웃 (POST /api/auth/logout)
- 내 정보 (GET /api/auth/me)

전략: 디트로이트파 (Classicist)
- 외부 시스템(DB)만 Mock
- 내부 객체(Pydantic, FastAPI 라우팅, bcrypt, JWT)는 진짜 사용
- "응답 상태 코드와 데이터가 올바른가?" 를 검증
"""
import pytest
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def auth_client(monkeypatch, tmp_path):
    """Auth 테스트용 AsyncClient (DB mock, VertexAI/QueueWorker mock)"""
    storage = tmp_path / "storage"
    (storage / "images").mkdir(parents=True)
    (storage / "videos").mkdir(parents=True)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("STORAGE_PATH", str(storage))

    from app.config import get_settings
    get_settings.cache_clear()

    # vertex_ai, queue_worker 모듈 mock (import 시 GCP 인증 회피)
    mock_vertex_module = MagicMock()
    monkeypatch.setitem(sys.modules, "app.services.vertex_ai", mock_vertex_module)

    mock_qw_module = MagicMock()
    mock_qw_module.queue_worker.start = AsyncMock()
    mock_qw_module.queue_worker.stop = AsyncMock()
    mock_qw_module.queue_worker.enqueue = AsyncMock()
    mock_qw_module.queue_worker.pending_count = 0
    monkeypatch.setitem(sys.modules, "app.services.queue_worker", mock_qw_module)

    for mod_name in list(sys.modules):
        if mod_name.startswith("app.routers") or mod_name.startswith("app.services.auth") or mod_name == "app.main":
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    with patch("app.db.connect_db", new_callable=AsyncMock), \
         patch("app.db.disconnect_db", new_callable=AsyncMock), \
         patch("app.db.db") as mock_db:

        # 기본 DB mock 설정 (모든 async 메서드를 AsyncMock으로)
        mock_db.user.find_unique = AsyncMock(return_value=None)
        mock_db.user.create = AsyncMock()
        mock_db.asset.find_first = AsyncMock(return_value=None)
        mock_db.job.create = AsyncMock(return_value=MagicMock(id=1, jobId="test"))
        mock_db.refreshtoken.find_unique = AsyncMock(return_value=None)
        mock_db.refreshtoken.create = AsyncMock()
        mock_db.refreshtoken.delete = AsyncMock()
        mock_db.refreshtoken.delete_many = AsyncMock()

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, mock_db, app

    get_settings.cache_clear()


# ===== 회원가입 =====

async def test_signup_success(auth_client):
    """정상 회원가입 → 201 + 유저 정보 반환"""
    client, mock_db, _ = auth_client

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "new@test.com"
    mock_user.username = "newuser"
    mock_db.user.create = AsyncMock(return_value=mock_user)

    response = await client.post("/api/auth/signup", json={
        "email": "new@test.com",
        "username": "newuser",
        "password": "password123",
    })

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@test.com"
    assert data["username"] == "newuser"
    assert "id" in data
    assert "password" not in data  # 비밀번호는 응답에 미포함


async def test_signup_duplicate_email(auth_client):
    """중복 이메일 → 409"""
    client, mock_db, _ = auth_client

    existing_user = MagicMock()
    existing_user.email = "taken@test.com"
    # 첫 번째 find_unique(email) → 중복 발견
    mock_db.user.find_unique = AsyncMock(return_value=existing_user)

    response = await client.post("/api/auth/signup", json={
        "email": "taken@test.com",
        "username": "newuser",
        "password": "password123",
    })

    assert response.status_code == 409
    assert "이메일" in response.json()["detail"]


async def test_signup_duplicate_username(auth_client):
    """중복 유저네임 → 409"""
    client, mock_db, _ = auth_client

    # 첫 번째 find_unique(email) → None, 두 번째 find_unique(username) → 중복
    mock_db.user.find_unique = AsyncMock(
        side_effect=[None, MagicMock(username="taken")]
    )

    response = await client.post("/api/auth/signup", json={
        "email": "new@test.com",
        "username": "taken",
        "password": "password123",
    })

    assert response.status_code == 409
    assert "유저네임" in response.json()["detail"]


async def test_signup_missing_fields(auth_client):
    """필수 필드 누락 → 422"""
    client, _, _ = auth_client

    response = await client.post("/api/auth/signup", json={
        "email": "new@test.com",
    })

    assert response.status_code == 422


# ===== 로그인 =====

async def test_login_success(auth_client):
    """올바른 자격 증명 → 200 + access_token + refresh_token"""
    client, mock_db, _ = auth_client

    from app.services.auth import hash_password
    hashed = hash_password("correct_password")

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.email = "user@test.com"
    mock_user.password = hashed
    mock_db.user.find_unique = AsyncMock(return_value=mock_user)
    mock_db.refreshtoken.create = AsyncMock()

    response = await client.post("/api/auth/login", json={
        "email": "user@test.com",
        "password": "correct_password",
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


async def test_login_wrong_password(auth_client):
    """틀린 비밀번호 → 401"""
    client, mock_db, _ = auth_client

    from app.services.auth import hash_password
    hashed = hash_password("correct_password")

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.password = hashed
    mock_db.user.find_unique = AsyncMock(return_value=mock_user)

    response = await client.post("/api/auth/login", json={
        "email": "user@test.com",
        "password": "wrong_password",
    })

    assert response.status_code == 401


async def test_login_nonexistent_email(auth_client):
    """존재하지 않는 이메일 → 401"""
    client, mock_db, _ = auth_client

    mock_db.user.find_unique = AsyncMock(return_value=None)

    response = await client.post("/api/auth/login", json={
        "email": "nobody@test.com",
        "password": "anything",
    })

    assert response.status_code == 401


async def test_login_missing_password(auth_client):
    """비밀번호 누락 → 422"""
    client, _, _ = auth_client

    response = await client.post("/api/auth/login", json={
        "email": "user@test.com",
    })

    assert response.status_code == 422


# ===== 토큰 갱신 =====

async def test_refresh_success(auth_client):
    """유효한 RT → 새 토큰 쌍 반환"""
    client, mock_db, _ = auth_client

    mock_rt = MagicMock()
    mock_rt.id = 1
    mock_rt.userId = 42
    mock_rt.expiresAt = datetime.now(timezone.utc) + timedelta(days=7)

    mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
    mock_db.refreshtoken.delete = AsyncMock()
    mock_db.refreshtoken.create = AsyncMock()

    response = await client.post("/api/auth/refresh", json={
        "refresh_token": "valid-rt-uuid",
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


async def test_refresh_reused_token(auth_client):
    """이미 사용된 RT → 탈취 감지 401"""
    client, mock_db, _ = auth_client

    mock_db.refreshtoken.find_unique = AsyncMock(return_value=None)

    response = await client.post("/api/auth/refresh", json={
        "refresh_token": "already-used-token",
    })

    assert response.status_code == 401
    assert "token_reuse_detected" in response.json()["detail"]


async def test_refresh_expired_token(auth_client):
    """만료된 RT → 401"""
    client, mock_db, _ = auth_client

    mock_rt = MagicMock()
    mock_rt.id = 1
    mock_rt.userId = 1
    mock_rt.expiresAt = datetime.now(timezone.utc) - timedelta(days=1)

    mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
    mock_db.refreshtoken.delete = AsyncMock()

    response = await client.post("/api/auth/refresh", json={
        "refresh_token": "expired-token",
    })

    assert response.status_code == 401


# ===== 로그아웃 =====

async def test_logout_success(auth_client):
    """정상 로그아웃 → 200"""
    client, mock_db, _ = auth_client

    mock_rt = MagicMock()
    mock_rt.id = 1
    mock_db.refreshtoken.find_unique = AsyncMock(return_value=mock_rt)
    mock_db.refreshtoken.delete = AsyncMock()

    response = await client.post("/api/auth/logout", json={
        "refresh_token": "valid-rt-uuid",
    })

    assert response.status_code == 200
    assert "로그아웃" in response.json()["message"]


async def test_logout_invalid_token_still_200(auth_client):
    """존재하지 않는 RT로 로그아웃 → 에러 없이 200 (멱등성)"""
    client, mock_db, _ = auth_client

    mock_db.refreshtoken.find_unique = AsyncMock(return_value=None)

    response = await client.post("/api/auth/logout", json={
        "refresh_token": "nonexistent-token",
    })

    assert response.status_code == 200


# ===== 내 정보 =====

async def test_me_with_valid_token(auth_client):
    """유효한 Access Token → 200 + 유저 정보"""
    client, mock_db, app = auth_client

    from app.services.auth import create_access_token

    mock_user = MagicMock()
    mock_user.id = 42
    mock_user.email = "me@test.com"
    mock_user.username = "myname"
    mock_db.user.find_unique = AsyncMock(return_value=mock_user)

    token = create_access_token(user_id=42)

    response = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {token}",
    })

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 42
    assert data["email"] == "me@test.com"
    assert data["username"] == "myname"


async def test_me_without_token(auth_client):
    """토큰 없이 요청 → 403"""
    client, _, _ = auth_client

    response = await client.get("/api/auth/me")

    assert response.status_code == 403


async def test_me_with_invalid_token(auth_client):
    """유효하지 않은 토큰 → 401"""
    client, _, _ = auth_client

    response = await client.get("/api/auth/me", headers={
        "Authorization": "Bearer invalid-jwt-token",
    })

    assert response.status_code == 401


async def test_me_with_deleted_user(auth_client):
    """토큰은 유효하지만 유저가 삭제됨 → 401"""
    client, mock_db, _ = auth_client

    from app.services.auth import create_access_token
    token = create_access_token(user_id=999)

    mock_db.user.find_unique = AsyncMock(return_value=None)

    response = await client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {token}",
    })

    assert response.status_code == 401
