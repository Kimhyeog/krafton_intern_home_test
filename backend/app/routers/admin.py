from fastapi import APIRouter, Depends
from app.services.auth import get_current_user
from app.services.vertex_ai import IMAGE_SEMAPHORE, VIDEO_SEMAPHORE
from app.services.queue_worker import queue_worker
from app.db import db

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/queue-status")
async def queue_status(current_user=Depends(get_current_user)):
    """
    큐잉 시스템 모니터링 엔드포인트.
    Semaphore 상태, 큐 대기 수, DB 기반 Job 통계를 반환한다.
    """
    image_max = 10
    video_max = 3

    image_available = IMAGE_SEMAPHORE._value
    video_available = VIDEO_SEMAPHORE._value

    queued_count = await db.job.count(where={"status": "queued"})
    processing_count = await db.job.count(where={"status": "processing"})
    completed_count = await db.job.count(where={"status": "completed"})
    failed_count = await db.job.count(where={"status": "failed"})

    return {
        "semaphore": {
            "image": {
                "max": image_max,
                "available": image_available,
                "in_use": image_max - image_available,
            },
            "video": {
                "max": video_max,
                "available": video_available,
                "in_use": video_max - video_available,
            },
        },
        "queue": {
            "pending": queue_worker.pending_count,
        },
        "jobs": {
            "queued": queued_count,
            "processing": processing_count,
            "completed": completed_count,
            "failed": failed_count,
        },
    }
