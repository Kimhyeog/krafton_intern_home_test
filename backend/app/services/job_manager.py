from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

@dataclass
class JobInfo:
    job_id: str
    status: str = "pending"  # pending, processing, completed, failed
    asset_id: Optional[int] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

class JobManager:
    def __init__(self):
        self._jobs: Dict[str, JobInfo] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, job_id: str) -> JobInfo:
        async with self._lock:
            job = JobInfo(job_id=job_id)
            self._jobs[job_id] = job
            return job

    async def update_job(self, job_id: str, **kwargs) -> None:
        async with self._lock:
            if job_id in self._jobs:
                for key, value in kwargs.items():
                    setattr(self._jobs[job_id], key, value)
                self._jobs[job_id]._event.set()

    async def get_job(self, job_id: str) -> Optional[JobInfo]:
        return self._jobs.get(job_id)

    def get_stats(self) -> Dict[str, int]:
        """Job 상태별 집계 반환"""
        stats = {"pending": 0, "processing": 0, "completed": 0, "failed": 0}
        for job in self._jobs.values():
            if job.status in stats:
                stats[job.status] += 1
        return stats

job_manager = JobManager()
