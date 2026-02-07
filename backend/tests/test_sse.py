"""
Phase 8: SSE (Server-Sent Events) 테스트

테스트 대상:
- backend/app/services/job_manager.py — asyncio.Event 알림 메커니즘
- backend/app/routers/generate.py — GET /jobs/{job_id}/stream SSE 엔드포인트

전략: 디트로이트파 (Classicist)
- Part 1: asyncio.Event 단위 테스트 (외부 의존성 없음)
- Part 2: SSE 엔드포인트 통합 테스트 (DB/VertexAI만 Mock)
"""
import pytest
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

from app.services.job_manager import JobManager


# ═══════════════════════════════════════════════════════
# Part 1: asyncio.Event 상태 알림 단위 테스트
# ═══════════════════════════════════════════════════════


async def test_job_has_event_field():
    """JobInfo 생성 시 asyncio.Event가 자동 포함되는지 검증"""
    jm = JobManager()
    job = await jm.create_job("event-001")

    assert hasattr(job, "_event")
    assert isinstance(job._event, asyncio.Event)
    assert not job._event.is_set()
    print("\n✅ [Event] JobInfo에 _event 필드 존재, 초기값 is_set()=False")


async def test_event_set_on_update():
    """update_job 호출 시 _event.set()이 트리거되는지 검증"""
    jm = JobManager()
    job = await jm.create_job("event-002")
    assert not job._event.is_set()

    await jm.update_job("event-002", status="processing")
    assert job._event.is_set()
    print("\n✅ [Event] update_job 호출 → _event.is_set()=True 확인")


async def test_event_wait_unblocks_on_update():
    """await _event.wait()가 update_job 시 즉시 해제되는지 검증"""
    jm = JobManager()
    job = await jm.create_job("event-003")

    unblocked = False

    async def waiter():
        nonlocal unblocked
        await job._event.wait()
        unblocked = True

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)
    assert not unblocked  # 아직 대기 중

    await jm.update_job("event-003", status="processing")
    await asyncio.sleep(0.05)
    assert unblocked  # event.set()으로 해제됨

    await task
    print("\n✅ [Event] event.wait() → update_job() → 즉시 해제 확인")


async def test_event_multiple_state_transitions():
    """clear → wait → set 사이클 반복 동작 검증 (SSE 스트림 시뮬레이션)"""
    jm = JobManager()
    job = await jm.create_job("event-004")

    received = []

    async def sse_simulator():
        """SSE event_generator 로직을 그대로 재현"""
        while True:
            job._event.clear()
            await job._event.wait()
            received.append(job.status)
            if job.status in ("completed", "failed"):
                return

    task = asyncio.create_task(sse_simulator())

    await asyncio.sleep(0.05)
    await jm.update_job("event-004", status="processing")
    await asyncio.sleep(0.05)
    await jm.update_job("event-004", status="completed", result_url="/storage/videos/test.mp4")
    await asyncio.sleep(0.05)

    await task

    assert received == ["processing", "completed"]
    print(f"\n✅ [Event] 상태 전이 수신: {received} (pending→processing→completed)")


async def test_event_failed_ends_stream():
    """failed 상태가 SSE 스트림을 정상 종료하는지 검증"""
    jm = JobManager()
    job = await jm.create_job("event-005")

    received = []

    async def sse_simulator():
        while True:
            job._event.clear()
            await job._event.wait()
            received.append(job.status)
            if job.status in ("completed", "failed"):
                return

    task = asyncio.create_task(sse_simulator())

    await asyncio.sleep(0.05)
    await jm.update_job("event-005", status="processing")
    await asyncio.sleep(0.05)
    await jm.update_job("event-005", status="failed", error_message="테스트 에러")
    await asyncio.sleep(0.05)

    await task

    assert received == ["processing", "failed"]
    assert job.error_message == "테스트 에러"
    print(f"\n✅ [Event] failed 전이 수신: {received}, 에러: '{job.error_message}'")


async def test_multiple_jobs_events_independent():
    """여러 Job의 _event가 서로 간섭하지 않는지 검증"""
    jm = JobManager()
    job_a = await jm.create_job("event-a")
    job_b = await jm.create_job("event-b")

    # job_a만 업데이트
    await jm.update_job("event-a", status="processing")

    assert job_a._event.is_set()
    assert not job_b._event.is_set()  # job_b는 영향 없음
    print("\n✅ [Event] Job A 업데이트 → Job B _event 영향 없음 (독립성)")


# ═══════════════════════════════════════════════════════
# Part 2: SSE 엔드포인트 통합 테스트
# ═══════════════════════════════════════════════════════


@pytest.fixture
async def sse_client(monkeypatch, tmp_path):
    """SSE 테스트용 AsyncClient (DB + VertexAI mock)"""
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

    for mod_name in list(sys.modules):
        if mod_name.startswith("app.routers") or mod_name == "app.main":
            monkeypatch.delitem(sys.modules, mod_name, raising=False)

    with patch("app.db.connect_db", new_callable=AsyncMock), \
         patch("app.db.disconnect_db", new_callable=AsyncMock), \
         patch("app.db.db") as mock_db:

        mock_db.asset.find_first = AsyncMock(return_value=None)

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

    get_settings.cache_clear()


def parse_sse_events(text: str) -> list[dict]:
    """SSE 응답 텍스트에서 data 이벤트를 파싱"""
    events = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


async def test_sse_404_for_unknown_job(sse_client):
    """존재하지 않는 job_id로 SSE 요청 시 404 반환"""
    response = await sse_client.get("/api/generate/jobs/nonexistent-id/stream")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"
    print("\n✅ [SSE 엔드포인트] 존재하지 않는 job_id → 404 반환")


async def test_sse_completed_job_sends_single_event(sse_client):
    """이미 completed된 Job에 SSE 연결 시 이벤트 1개 후 스트림 종료"""
    from app.services.job_manager import job_manager

    await job_manager.create_job("sse-completed")
    await job_manager.update_job(
        "sse-completed",
        status="completed",
        asset_id=42,
        result_url="/storage/images/test.png",
    )

    response = await sse_client.get("/api/generate/jobs/sse-completed/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert response.headers["cache-control"] == "no-cache"

    events = parse_sse_events(response.text)
    assert len(events) == 1
    assert events[0]["status"] == "completed"
    assert events[0]["result_url"] == "/storage/images/test.png"
    assert events[0]["asset_id"] == 42
    print(f"\n✅ [SSE 엔드포인트] completed Job → 이벤트 1개 수신, content-type=text/event-stream")


async def test_sse_failed_job_sends_single_event(sse_client):
    """이미 failed된 Job에 SSE 연결 시 이벤트 1개 후 스트림 종료"""
    from app.services.job_manager import job_manager

    await job_manager.create_job("sse-failed")
    await job_manager.update_job(
        "sse-failed",
        status="failed",
        error_message="테스트 실패 메시지",
    )

    response = await sse_client.get("/api/generate/jobs/sse-failed/stream")

    events = parse_sse_events(response.text)
    assert len(events) == 1
    assert events[0]["status"] == "failed"
    assert events[0]["error_message"] == "테스트 실패 메시지"
    print(f"\n✅ [SSE 엔드포인트] failed Job → 이벤트 1개 수신 (에러: '{events[0]['error_message']}')")


async def test_sse_streams_realtime_state_changes(sse_client):
    """SSE로 pending→processing→completed 상태 전이를 실시간 수신"""
    from app.services.job_manager import job_manager

    await job_manager.create_job("sse-stream")

    async def updater():
        await asyncio.sleep(0.1)
        await job_manager.update_job("sse-stream", status="processing")
        await asyncio.sleep(0.1)
        await job_manager.update_job(
            "sse-stream",
            status="completed",
            asset_id=99,
            result_url="/storage/videos/stream-test.mp4",
        )

    update_task = asyncio.create_task(updater())
    response = await asyncio.wait_for(
        sse_client.get("/api/generate/jobs/sse-stream/stream"),
        timeout=5.0,
    )
    await update_task

    events = parse_sse_events(response.text)

    assert len(events) == 3  # pending, processing, completed
    assert events[0]["status"] == "pending"
    assert events[1]["status"] == "processing"
    assert events[2]["status"] == "completed"
    assert events[2]["result_url"] == "/storage/videos/stream-test.mp4"
    print(f"\n✅ [SSE 엔드포인트] 실시간 상태 전이: {[e['status'] for e in events]}")


async def test_sse_streams_failed_transition(sse_client):
    """SSE로 pending→processing→failed 전이를 수신하고 스트림 종료"""
    from app.services.job_manager import job_manager

    await job_manager.create_job("sse-fail-stream")

    async def updater():
        await asyncio.sleep(0.1)
        await job_manager.update_job("sse-fail-stream", status="processing")
        await asyncio.sleep(0.1)
        await job_manager.update_job(
            "sse-fail-stream",
            status="failed",
            error_message="Vertex AI 에러",
        )

    update_task = asyncio.create_task(updater())
    response = await asyncio.wait_for(
        sse_client.get("/api/generate/jobs/sse-fail-stream/stream"),
        timeout=5.0,
    )
    await update_task

    events = parse_sse_events(response.text)

    assert len(events) == 3  # pending, processing, failed
    assert events[0]["status"] == "pending"
    assert events[1]["status"] == "processing"
    assert events[2]["status"] == "failed"
    assert events[2]["error_message"] == "Vertex AI 에러"
    print(f"\n✅ [SSE 엔드포인트] failed 전이: {[e['status'] for e in events]}, 에러: '{events[2]['error_message']}'")
