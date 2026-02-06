import pytest
from app.services.job_manager import JobManager


@pytest.fixture
def job_manager():
    """매 테스트마다 새로운 JobManager 인스턴스 생성"""
    return JobManager()
