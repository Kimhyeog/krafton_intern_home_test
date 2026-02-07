"""
Generate API 엔드포인트 통합 테스트

테스트 대상: backend/app/routers/generate.py
- 엔드포인트 응답 형식 검증
- job_id 반환 + 초기 상태 검증
- Vertex AI 호출은 mock 처리

유형: Integration Test — DB/VertexAI만 Mock, JobManager/Pydantic은 진짜 사용
전략: 디트로이트파 (Classicist)
"""
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(monkeypatch, tmp_path):
    """테스트용 AsyncClient 생성 (DB + VertexAI mock + Auth override)"""
    # 1. 테스트용 storage 디렉터리 생성
    storage = tmp_path / "storage"
    (storage / "images").mkdir(parents=True)
    (storage / "videos").mkdir(parents=True)

    # 2. Settings 검증 통과를 위한 환경변수 설정
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    monkeypatch.setenv("STORAGE_PATH", str(storage))

    # 3. Settings lru_cache 초기화 (새 환경변수 반영)
    from app.config import get_settings
    get_settings.cache_clear()

    # 4. vertex_ai 모듈을 mock으로 주입 (GCP 인증 없이 테스트)
    #    모듈 레벨에서 VertexAIService()가 인스턴스화되므로
    #    patch()로는 import 전에 개입할 수 없음 → sys.modules 직접 주입
    mock_vertex_module = MagicMock()
    monkeypatch.setitem(sys.modules, "app.services.vertex_ai", mock_vertex_module)

    # 4-1. queue_worker 모듈도 mock으로 주입 (vertex_ai를 import하므로)
    mock_queue_worker_module = MagicMock()
    mock_queue_worker_module.queue_worker.enqueue = AsyncMock()
    mock_queue_worker_module.queue_worker.start = AsyncMock()
    mock_queue_worker_module.queue_worker.stop = AsyncMock()
    mock_queue_worker_module.queue_worker.pending_count = 0
    monkeypatch.setitem(sys.modules, "app.services.queue_worker", mock_queue_worker_module)

    # 5. 의존 모듈 캐시 클리어 → 재임포트 시 mock 사용
    for mod_name in list(sys.modules):
        if mod_name.startswith("app.routers") or mod_name == "app.main":
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    # 6. DB mock 적용 + app 재임포트
    with patch("app.db.connect_db", new_callable=AsyncMock), \
         patch("app.db.disconnect_db", new_callable=AsyncMock), \
         patch("app.db.db") as mock_db:

        # DB 캐시 조회 mock: find_first → None (캐시 미스)
        mock_db.asset.find_first = AsyncMock(return_value=None)
        # DB Job 생성 mock (QueueWorker용)
        mock_db.job.create = AsyncMock(return_value=MagicMock(id=1, jobId="test"))

        from app.main import app

        # 7. 인증 우회: get_current_user를 mock 사용자로 override
        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.email = "test@test.com"
        mock_user.username = "testuser"

        from app.services.auth import get_current_user
        app.dependency_overrides[get_current_user] = lambda: mock_user

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

        app.dependency_overrides.clear()

    get_settings.cache_clear()


# ===== Health Check =====

async def test_health_check(client: AsyncClient):
    """헬스체크 엔드포인트 정상 응답"""
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


# ===== Text-to-Image =====

async def test_text_to_image_returns_job_id(client: AsyncClient):
    """text-to-image 요청 시 job_id와 pending/completed 상태 반환"""
    response = await client.post(
        "/api/generate/text-to-image",
        json={
            "prompt": "a fantasy sword",
            "model": "imagen-3.0-fast-generate-001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("pending", "completed")
    assert "created_at" in data


async def test_text_to_image_missing_prompt(client: AsyncClient):
    """prompt 없이 요청하면 422 반환"""
    response = await client.post(
        "/api/generate/text-to-image",
        json={"model": "imagen-3.0-fast-generate-001"},
    )

    assert response.status_code == 422


async def test_text_to_image_missing_model(client: AsyncClient):
    """model 없이 요청하면 422 반환"""
    response = await client.post(
        "/api/generate/text-to-image",
        json={"prompt": "a sword"},
    )

    assert response.status_code == 422


# ===== Text-to-Video =====

async def test_text_to_video_returns_job_id(client: AsyncClient):
    """text-to-video 요청 시 job_id 반환"""
    response = await client.post(
        "/api/generate/text-to-video",
        json={
            "prompt": "a dragon flying",
            "model": "veo-3.0-fast-generate-001",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] in ("pending", "completed")


# ===== Job Status =====

async def test_get_job_status_not_found(client: AsyncClient):
    """존재하지 않는 job_id로 조회하면 404 반환"""
    response = await client.get("/api/generate/jobs/nonexistent-uuid")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
