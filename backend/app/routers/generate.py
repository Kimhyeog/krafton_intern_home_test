from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime
import json
from app.db import db
from app.services.job_manager import job_manager
from app.services.vertex_ai import vertex_ai_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["generate"])

class GenerateRequest(BaseModel):
    prompt: str
    model: str

class GenerateResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    asset_id: Optional[int] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None

# ===== 캐시 조회 =====

async def find_cached_asset(prompt: str, model: str, asset_type: str) -> Optional[dict]:
    """
    동일 prompt + model + assetType 조합의 기존 에셋을 DB에서 검색.
    캐시 히트 시 asset_id와 result_url을 반환, 없으면 None.
    """
    normalized_prompt = prompt.strip().lower()

    asset = await db.asset.find_first(
        where={
            "prompt": normalized_prompt,
            "model": model,
            "assetType": asset_type,
        },
        order={"createdAt": "desc"},
    )

    if asset and asset.filePath:
        logger.info(f"[Cache] HIT - prompt='{normalized_prompt[:30]}...', model={model}")
        return {
            "asset_id": asset.id,
            "result_url": asset.filePath,
        }

    logger.info(f"[Cache] MISS - prompt='{normalized_prompt[:30]}...', model={model}")
    return None


# ===== Background Tasks =====

async def process_image_generation(job_id: str, prompt: str, model: str):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_image(prompt, job_id)
        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "image"
        })
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)
    except Exception as e:
        await job_manager.update_job(job_id, status="failed", error_message=str(e))

async def process_video_from_text(job_id: str, prompt: str, model: str):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_video_from_text(prompt, job_id)
        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "video"
        })
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)
    except Exception as e:
        await job_manager.update_job(job_id, status="failed", error_message=str(e))

async def process_video_from_image(job_id: str, prompt: str, model: str, image_bytes: bytes, mime_type: str):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_video_from_image(prompt, image_bytes, job_id, mime_type)
        normalized_prompt = prompt.strip().lower()
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": normalized_prompt,
            "model": model,
            "assetType": "video"
        })
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)
    except Exception as e:
        await job_manager.update_job(job_id, status="failed", error_message=str(e))

# ===== API Endpoints =====

@router.post("/text-to-image", response_model=GenerateResponse)
async def text_to_image(request: GenerateRequest, background_tasks: BackgroundTasks):
    # 캐시 확인: 동일 prompt + model 조합이 DB에 있는지 검색
    cached = await find_cached_asset(request.prompt, request.model, "image")
    if cached:
        job_id = str(uuid4())
        job = await job_manager.create_job(job_id)
        await job_manager.update_job(
            job_id,
            status="completed",
            asset_id=cached["asset_id"],
            result_url=cached["result_url"],
        )
        return GenerateResponse(job_id=job_id, status="completed", created_at=job.created_at)

    # 캐시 미스: 새로 생성
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    background_tasks.add_task(process_image_generation, job_id, request.prompt, request.model)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.post("/text-to-video", response_model=GenerateResponse)
async def text_to_video(request: GenerateRequest, background_tasks: BackgroundTasks):
    # 캐시 확인
    cached = await find_cached_asset(request.prompt, request.model, "video")
    if cached:
        job_id = str(uuid4())
        job = await job_manager.create_job(job_id)
        await job_manager.update_job(
            job_id,
            status="completed",
            asset_id=cached["asset_id"],
            result_url=cached["result_url"],
        )
        return GenerateResponse(job_id=job_id, status="completed", created_at=job.created_at)

    # 캐시 미스
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    background_tasks.add_task(process_video_from_text, job_id, request.prompt, request.model)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.post("/image-to-video", response_model=GenerateResponse)
async def image_to_video(
    prompt: str = Form(...),
    model: str = Form(...),
    image: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
):
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    image_bytes = await image.read()
    mime_type = image.content_type or "image/png"
    background_tasks.add_task(process_video_from_image, job_id, prompt, model, image_bytes, mime_type)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        asset_id=job.asset_id,
        result_url=job.result_url,
        error_message=job.error_message
    )

@router.get("/jobs/{job_id}/stream")
async def stream_job_status(job_id: str):
    """SSE 엔드포인트: Job 상태 변화를 실시간 스트리밍"""
    job = await job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    def _job_data(j) -> str:
        return json.dumps({
            "job_id": j.job_id,
            "status": j.status,
            "asset_id": j.asset_id,
            "result_url": j.result_url,
            "error_message": j.error_message,
        })

    async def event_generator():
        # 현재 상태를 즉시 전송
        yield f"data: {_job_data(job)}\n\n"

        # 이미 완료 상태이면 스트림 종료
        if job.status in ("completed", "failed"):
            return

        # 상태 변화를 대기하며 전송
        while True:
            job._event.clear()
            await job._event.wait()

            yield f"data: {_job_data(job)}\n\n"

            if job.status in ("completed", "failed"):
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
