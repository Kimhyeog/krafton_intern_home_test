"""
에셋 관리 API 엔드포인트 통합 테스트

테스트 대상: backend/app/routers/assets.py
- 목록 조회 (GET /api/assets/)
- 상세 조회 (GET /api/assets/{id})
- 삭제 (DELETE /api/assets/{id})

전략: 디트로이트파 (Classicist)
- 외부 시스템(DB, 파일시스템)만 Mock
- 내부 객체(FastAPI 라우팅, Pydantic)는 진짜 사용
- "응답 상태 코드와 데이터가 올바른가?" + "본인 에셋만 접근 가능한가?" 를 검증
"""
import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest.fixture
async def assets_client(monkeypatch, tmp_path):
    """Assets 테스트용 AsyncClient (DB mock + 인증 override)"""
    storage = tmp_path / "storage"
    (storage / "images").mkdir(parents=True)
    (storage / "videos").mkdir(parents=True)

    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("STORAGE_PATH", str(storage))

    from app.config import get_settings
    get_settings.cache_clear()

    mock_vertex_module = MagicMock()
    monkeypatch.setitem(sys.modules, "app.services.vertex_ai", mock_vertex_module)

    mock_qw_module = MagicMock()
    mock_qw_module.queue_worker.start = AsyncMock()
    mock_qw_module.queue_worker.stop = AsyncMock()
    mock_qw_module.queue_worker.enqueue = AsyncMock()
    mock_qw_module.queue_worker.pending_count = 0
    monkeypatch.setitem(sys.modules, "app.services.queue_worker", mock_qw_module)

    for mod_name in list(sys.modules):
        if mod_name.startswith("app.routers") or mod_name == "app.main":
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    with patch("app.db.connect_db", new_callable=AsyncMock), \
         patch("app.db.disconnect_db", new_callable=AsyncMock), \
         patch("app.db.db") as mock_db:

        mock_db.asset.find_first = AsyncMock(return_value=None)
        mock_db.job.create = AsyncMock(return_value=MagicMock(id=1, jobId="test"))

        from app.main import app

        # 인증된 사용자 (user_id=1)
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@test.com"
        mock_user.username = "testuser"

        from app.services.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, mock_db, str(storage)

        app.dependency_overrides.clear()

    get_settings.cache_clear()


# ===== 목록 조회 =====

async def test_list_assets_returns_array(assets_client):
    """에셋 목록 → 200 + 배열"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_many = AsyncMock(return_value=[])

    response = await client.get("/api/assets/")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_list_assets_filters_by_user(assets_client):
    """본인 에셋만 조회 (userId 필터)"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_many = AsyncMock(return_value=[])

    await client.get("/api/assets/")

    call_args = mock_db.asset.find_many.call_args
    assert call_args[1]["where"]["userId"] == 1  # fixture의 mock_user.id


async def test_list_assets_ordered_by_newest(assets_client):
    """최신순 정렬"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_many = AsyncMock(return_value=[])

    await client.get("/api/assets/")

    call_args = mock_db.asset.find_many.call_args
    assert call_args[1]["order"] == {"createdAt": "desc"}


async def test_list_assets_pagination(assets_client):
    """skip/limit 파라미터 전달"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_many = AsyncMock(return_value=[])

    await client.get("/api/assets/?skip=10&limit=5")

    call_args = mock_db.asset.find_many.call_args
    assert call_args[1]["skip"] == 10
    assert call_args[1]["take"] == 5


async def test_list_assets_returns_asset_data(assets_client):
    """에셋 데이터 정상 반환"""
    client, mock_db, _ = assets_client

    mock_asset = MagicMock()
    mock_asset.id = 1
    mock_asset.jobId = "abc-123"
    mock_asset.filePath = "/storage/images/abc-123.png"
    mock_asset.prompt = "a sword"
    mock_asset.model = "imagen-3.0-fast-generate-001"
    mock_asset.assetType = "image"
    mock_asset.createdAt = "2025-01-01T00:00:00Z"
    mock_asset.fileSize = None
    mock_asset.duration = None
    mock_asset.userId = 1

    # find_many가 dict-serializable 객체를 반환하도록
    # Prisma 모델은 자동으로 JSON 직렬화되므로, dict 사용
    mock_db.asset.find_many = AsyncMock(return_value=[{
        "id": 1,
        "jobId": "abc-123",
        "filePath": "/storage/images/abc-123.png",
        "prompt": "a sword",
        "model": "imagen-3.0-fast-generate-001",
        "assetType": "image",
        "createdAt": "2025-01-01T00:00:00Z",
        "fileSize": None,
        "duration": None,
        "userId": 1,
    }])

    response = await client.get("/api/assets/")

    assert response.status_code == 200
    assets = response.json()
    assert len(assets) == 1
    assert assets[0]["prompt"] == "a sword"


# ===== 상세 조회 =====

async def test_get_asset_success(assets_client):
    """본인 에셋 상세 조회 → 200"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_first = AsyncMock(return_value={
        "id": 5,
        "jobId": "xyz-789",
        "filePath": "/storage/images/xyz-789.png",
        "prompt": "a dragon",
        "model": "imagen-3.0-fast-generate-001",
        "assetType": "image",
        "createdAt": "2025-01-01T00:00:00Z",
        "fileSize": None,
        "duration": None,
        "userId": 1,
    })

    response = await client.get("/api/assets/5")

    assert response.status_code == 200
    assert response.json()["id"] == 5


async def test_get_asset_not_found(assets_client):
    """존재하지 않는 에셋 → 404"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_first = AsyncMock(return_value=None)

    response = await client.get("/api/assets/999")

    assert response.status_code == 404
    assert "에셋을 찾을 수 없습니다" in response.json()["detail"]


async def test_get_asset_other_user_returns_404(assets_client):
    """다른 사용자의 에셋 → 404 (권한 없음을 노출하지 않음)"""
    client, mock_db, _ = assets_client

    # find_first는 where에 userId 조건이 포함되어 있으므로
    # 다른 유저의 에셋은 결과가 None
    mock_db.asset.find_first = AsyncMock(return_value=None)

    response = await client.get("/api/assets/10")

    assert response.status_code == 404


async def test_get_asset_checks_user_id_in_query(assets_client):
    """상세 조회 시 userId 조건이 쿼리에 포함되는지 검증"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_first = AsyncMock(return_value=None)

    await client.get("/api/assets/7")

    call_args = mock_db.asset.find_first.call_args
    where = call_args[1]["where"]
    assert where["id"] == 7
    assert where["userId"] == 1


# ===== 삭제 =====

async def test_delete_asset_success(assets_client):
    """본인 에셋 삭제 → 200 + DB 삭제"""
    client, mock_db, storage_path = assets_client

    # 물리 파일 생성
    img_path = os.path.join(storage_path, "images", "del-test.png")
    with open(img_path, "wb") as f:
        f.write(b"fake image data")

    mock_asset = MagicMock()
    mock_asset.id = 3
    mock_asset.filePath = "/storage/images/del-test.png"
    mock_asset.userId = 1
    mock_db.asset.find_first = AsyncMock(return_value=mock_asset)
    mock_db.asset.delete = AsyncMock()

    response = await client.delete("/api/assets/3")

    assert response.status_code == 200
    assert "삭제" in response.json()["message"]
    mock_db.asset.delete.assert_called_once_with(where={"id": 3})


async def test_delete_asset_removes_physical_file(assets_client):
    """삭제 시 물리 파일도 삭제"""
    client, mock_db, storage_path = assets_client

    img_path = os.path.join(storage_path, "images", "to-delete.png")
    with open(img_path, "wb") as f:
        f.write(b"fake data")
    assert os.path.exists(img_path)

    mock_asset = MagicMock()
    mock_asset.id = 4
    mock_asset.filePath = "/storage/images/to-delete.png"
    mock_asset.userId = 1
    mock_db.asset.find_first = AsyncMock(return_value=mock_asset)
    mock_db.asset.delete = AsyncMock()

    await client.delete("/api/assets/4")

    assert not os.path.exists(img_path)


async def test_delete_asset_file_missing_no_error(assets_client):
    """물리 파일이 이미 없어도 에러 없이 처리 (멱등성)"""
    client, mock_db, _ = assets_client

    mock_asset = MagicMock()
    mock_asset.id = 5
    mock_asset.filePath = "/storage/images/already-gone.png"
    mock_asset.userId = 1
    mock_db.asset.find_first = AsyncMock(return_value=mock_asset)
    mock_db.asset.delete = AsyncMock()

    response = await client.delete("/api/assets/5")

    assert response.status_code == 200
    mock_db.asset.delete.assert_called_once()


async def test_delete_asset_not_found(assets_client):
    """존재하지 않는 에셋 삭제 → 404"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_first = AsyncMock(return_value=None)

    response = await client.delete("/api/assets/999")

    assert response.status_code == 404


async def test_delete_asset_other_user_returns_404(assets_client):
    """다른 유저 에셋 삭제 시도 → 404"""
    client, mock_db, _ = assets_client

    mock_db.asset.find_first = AsyncMock(return_value=None)

    response = await client.delete("/api/assets/10")

    assert response.status_code == 404
