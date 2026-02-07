"""
JobManager 단위 테스트

테스트 대상: backend/app/services/job_manager.py
- Job 생성, 상태 업데이트, 조회 로직 검증
- 외부 의존성 없음 (인메모리)

유형: Unit Test — 혼자 동작 가능 (dict만 사용)
"""
import pytest
from app.services.job_manager import JobManager, JobInfo

pytestmark = pytest.mark.unit


# ===== Job 생성 테스트 =====

async def test_create_job_returns_job_info(job_manager: JobManager):
    """job 생성 시 JobInfo 객체를 반환하는지 검증"""
    job = await job_manager.create_job("test-id-001")

    assert isinstance(job, JobInfo)
    assert job.job_id == "test-id-001"


async def test_create_job_initial_status_is_pending(job_manager: JobManager):
    """job 생성 시 초기 상태가 'pending'인지 검증"""
    job = await job_manager.create_job("test-id-002")

    assert job.status == "pending"
    assert job.asset_id is None
    assert job.result_url is None
    assert job.error_message is None


async def test_create_job_has_created_at(job_manager: JobManager):
    """job 생성 시 created_at 타임스탬프가 설정되는지 검증"""
    job = await job_manager.create_job("test-id-003")

    assert job.created_at is not None


# ===== Job 조회 테스트 =====

async def test_get_existing_job(job_manager: JobManager):
    """존재하는 job을 조회하면 해당 JobInfo를 반환"""
    await job_manager.create_job("existing-job")
    job = await job_manager.get_job("existing-job")

    assert job is not None
    assert job.job_id == "existing-job"


async def test_get_nonexistent_job_returns_none(job_manager: JobManager):
    """존재하지 않는 job 조회 시 None 반환"""
    job = await job_manager.get_job("nonexistent-id")

    assert job is None


# ===== Job 상태 업데이트 테스트 =====

async def test_update_job_status_to_processing(job_manager: JobManager):
    """job 상태를 processing으로 업데이트"""
    await job_manager.create_job("update-test-001")
    await job_manager.update_job("update-test-001", status="processing")

    job = await job_manager.get_job("update-test-001")
    assert job.status == "processing"


async def test_update_job_to_completed_with_result(job_manager: JobManager):
    """job 완료 시 asset_id와 result_url이 정상 설정되는지 검증"""
    await job_manager.create_job("update-test-002")
    await job_manager.update_job(
        "update-test-002",
        status="completed",
        asset_id=42,
        result_url="/storage/images/test.png",
    )

    job = await job_manager.get_job("update-test-002")
    assert job.status == "completed"
    assert job.asset_id == 42
    assert job.result_url == "/storage/images/test.png"


async def test_update_job_to_failed_with_error(job_manager: JobManager):
    """job 실패 시 error_message가 정상 설정되는지 검증"""
    await job_manager.create_job("update-test-003")
    await job_manager.update_job(
        "update-test-003",
        status="failed",
        error_message="Rate limit exceeded",
    )

    job = await job_manager.get_job("update-test-003")
    assert job.status == "failed"
    assert job.error_message == "Rate limit exceeded"


async def test_update_nonexistent_job_does_nothing(job_manager: JobManager):
    """존재하지 않는 job 업데이트 시 에러 없이 무시"""
    await job_manager.update_job("ghost-job", status="completed")
    job = await job_manager.get_job("ghost-job")
    assert job is None


# ===== 상태 전이 순서 테스트 =====

async def test_full_lifecycle_pending_to_completed(job_manager: JobManager):
    """pending → processing → completed 전체 라이프사이클 검증"""
    job_id = "lifecycle-001"

    # 1. 생성 (pending)
    job = await job_manager.create_job(job_id)
    assert job.status == "pending"

    # 2. 처리 시작 (processing)
    await job_manager.update_job(job_id, status="processing")
    job = await job_manager.get_job(job_id)
    assert job.status == "processing"

    # 3. 완료 (completed)
    await job_manager.update_job(
        job_id,
        status="completed",
        asset_id=1,
        result_url="/storage/images/test.png",
    )
    job = await job_manager.get_job(job_id)
    assert job.status == "completed"
    assert job.asset_id == 1


async def test_full_lifecycle_pending_to_failed(job_manager: JobManager):
    """pending → processing → failed 실패 라이프사이클 검증"""
    job_id = "lifecycle-002"

    await job_manager.create_job(job_id)
    await job_manager.update_job(job_id, status="processing")
    await job_manager.update_job(
        job_id,
        status="failed",
        error_message="Vertex AI error",
    )

    job = await job_manager.get_job(job_id)
    assert job.status == "failed"
    assert job.error_message == "Vertex AI error"
    assert job.asset_id is None


# ===== 복수 Job 관리 테스트 =====

async def test_multiple_jobs_are_independent(job_manager: JobManager):
    """여러 job이 서로 독립적으로 관리되는지 검증"""
    await job_manager.create_job("multi-001")
    await job_manager.create_job("multi-002")
    await job_manager.create_job("multi-003")

    await job_manager.update_job("multi-001", status="completed")
    await job_manager.update_job("multi-002", status="failed")
    # multi-003은 업데이트하지 않음

    job1 = await job_manager.get_job("multi-001")
    job2 = await job_manager.get_job("multi-002")
    job3 = await job_manager.get_job("multi-003")

    assert job1.status == "completed"
    assert job2.status == "failed"
    assert job3.status == "pending"  # 초기 상태 유지
