import os
import pytest
from app.services.job_manager import JobManager


@pytest.fixture(autouse=True, scope="session")
def _set_test_env():
    """모든 테스트에 필요한 최소 환경변수 설정 (마커별 단독 실행 지원)"""
    os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_db")


@pytest.fixture
def job_manager():
    """매 테스트마다 새로운 JobManager 인스턴스 생성"""
    return JobManager()
