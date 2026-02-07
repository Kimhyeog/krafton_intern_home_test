import asyncio
import json
import os
import logging
from datetime import datetime, timedelta, timezone

import aiofiles

from app.db import db
from app.services.job_manager import job_manager
from app.services.vertex_ai import vertex_ai_service
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ZOMBIE_THRESHOLD_HOURS = 24


class QueueWorker:
    def __init__(self):
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self, num_workers: int = 5):
        """Worker 코루틴 시작 + DB에서 미완료 작업 복구"""
        self._running = True

        await self._cleanup_zombie_jobs()
        await self._recover_from_db()

        for i in range(num_workers):
            task = asyncio.create_task(self._worker_loop(i))
            self._workers.append(task)

        logger.info(f"[QueueWorker] Started {num_workers} workers, queue size: {self._queue.qsize()}")

    async def stop(self):
        """모든 Worker graceful shutdown"""
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("[QueueWorker] All workers stopped")

    async def enqueue(self, job_id: str):
        """새 작업을 큐에 추가 (DB에는 이미 저장된 상태)"""
        await self._queue.put(job_id)
        logger.info(f"[QueueWorker] Enqueued job {job_id}, queue size: {self._queue.qsize()}")

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    # ===== Internal =====

    async def _recover_from_db(self):
        """서버 재시작 시 DB에서 미완료 작업 복구"""
        processing_jobs = await db.job.find_many(where={"status": "processing"})
        for job in processing_jobs:
            await db.job.update(where={"id": job.id}, data={"status": "queued"})
            logger.info(f"[Recovery] Reset processing -> queued: {job.jobId}")

        queued_jobs = await db.job.find_many(
            where={"status": "queued"},
            order={"createdAt": "asc"},
        )
        for job in queued_jobs:
            existing = await job_manager.get_job(job.jobId)
            if not existing:
                await job_manager.create_job(job.jobId)
            await self._queue.put(job.jobId)

        if queued_jobs:
            logger.info(f"[Recovery] Re-enqueued {len(queued_jobs)} jobs from DB")

    async def _cleanup_zombie_jobs(self):
        """24시간 이상 processing 상태인 좀비 작업을 failed로 처리"""
        threshold = datetime.now(timezone.utc) - timedelta(hours=ZOMBIE_THRESHOLD_HOURS)
        zombie_jobs = await db.job.find_many(
            where={"status": "processing", "updatedAt": {"lt": threshold}},
        )
        for job in zombie_jobs:
            await db.job.update(
                where={"id": job.id},
                data={
                    "status": "failed",
                    "errorMessage": f"좀비 작업: {ZOMBIE_THRESHOLD_HOURS}시간 이상 처리 중 상태로 방치됨",
                },
            )
            logger.warning(f"[Zombie] Marked as failed: {job.jobId}")

    async def _worker_loop(self, worker_id: int):
        """Worker 코루틴: 큐에서 작업을 꺼내 처리"""
        logger.info(f"[Worker-{worker_id}] Started")
        while self._running:
            try:
                try:
                    job_id = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                logger.info(f"[Worker-{worker_id}] Processing job {job_id}")
                await self._process_job(job_id, worker_id)
                self._queue.task_done()

            except asyncio.CancelledError:
                logger.info(f"[Worker-{worker_id}] Cancelled")
                break
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] Unhandled error: {e}", exc_info=True)

    async def _process_job(self, job_id: str, worker_id: int):
        """DB에서 Job 파라미터를 읽어 타입별 처리 분기"""
        db_job = await db.job.find_unique(where={"jobId": job_id})
        if not db_job:
            logger.error(f"[Worker-{worker_id}] Job not found in DB: {job_id}")
            return

        if db_job.status != "queued":
            logger.warning(f"[Worker-{worker_id}] Job {job_id} status is '{db_job.status}', skipping")
            return

        options = json.loads(db_job.options) if db_job.options else {}

        try:
            if db_job.jobType == "text-to-image":
                await self._process_image(job_id, db_job.prompt, db_job.model, db_job.userId, options)
            elif db_job.jobType == "text-to-video":
                await self._process_video_text(job_id, db_job.prompt, db_job.model, db_job.userId, options)
            elif db_job.jobType == "image-to-video":
                await self._process_video_image(
                    job_id, db_job.prompt, db_job.model, db_job.userId,
                    db_job.imagePath, db_job.mimeType or "image/png", options,
                )
            else:
                raise ValueError(f"Unknown job type: {db_job.jobType}")
        except Exception as e:
            logger.error(f"[Worker-{worker_id}] Job {job_id} failed: {e}")
            error_msg = str(e)
            await db.job.update(where={"jobId": job_id}, data={"status": "failed", "errorMessage": error_msg})
            await job_manager.update_job(job_id, status="failed", error_message=error_msg)

    async def _process_image(self, job_id: str, prompt: str, model: str, user_id: int, options: dict):
        await db.job.update(where={"jobId": job_id}, data={"status": "processing"})
        await job_manager.update_job(job_id, status="processing")

        result_url = await vertex_ai_service.generate_image(prompt, job_id, options=options or None)

        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "image",
            "userId": user_id,
        })

        await db.job.update(
            where={"jobId": job_id},
            data={"status": "completed", "assetId": asset.id, "resultUrl": result_url},
        )
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)

    async def _process_video_text(self, job_id: str, prompt: str, model: str, user_id: int, options: dict):
        await db.job.update(where={"jobId": job_id}, data={"status": "processing"})
        await job_manager.update_job(job_id, status="processing")

        result_url = await vertex_ai_service.generate_video_from_text(prompt, job_id, options=options or None)

        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "video",
            "userId": user_id,
        })

        await db.job.update(
            where={"jobId": job_id},
            data={"status": "completed", "assetId": asset.id, "resultUrl": result_url},
        )
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)

    async def _process_video_image(self, job_id: str, prompt: str, model: str, user_id: int,
                                    image_path: str, mime_type: str, options: dict):
        await db.job.update(where={"jobId": job_id}, data={"status": "processing"})
        await job_manager.update_job(job_id, status="processing")

        async with aiofiles.open(image_path, "rb") as f:
            image_bytes = await f.read()

        result_url = await vertex_ai_service.generate_video_from_image(
            prompt, image_bytes, job_id, mime_type, options=options or None,
        )

        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "video",
            "userId": user_id,
        })

        await db.job.update(
            where={"jobId": job_id},
            data={"status": "completed", "assetId": asset.id, "resultUrl": result_url},
        )
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)

        try:
            os.remove(image_path)
            logger.info(f"[Worker] Deleted temp image: {image_path}")
        except OSError as e:
            logger.warning(f"[Worker] Failed to delete temp image {image_path}: {e}")


queue_worker = QueueWorker()
