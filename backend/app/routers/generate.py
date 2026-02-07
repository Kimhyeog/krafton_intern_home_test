from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, Literal
from uuid import uuid4
from datetime import datetime
import json
from app.db import db
from app.services.job_manager import job_manager
from app.services.vertex_ai import vertex_ai_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/generate", tags=["generate"])


# ===== Request Models (Vertex AI Docs 기반 파라미터) =====

class ImageGenerateRequest(BaseModel):
    """Text-to-Image 요청 — Imagen 3.0 Python SDK 파라미터 (inspect.signature 검증 완료)"""
    prompt: str
    model: str

    # 화면 비율: 생성할 이미지의 종횡비
    aspect_ratio: Optional[Literal["1:1", "3:4", "4:3", "16:9", "9:16"]] = None
    # 네거티브 프롬프트: 생성 시 제외할 요소
    negative_prompt: Optional[str] = None
    # 시드: 동일 값 → 동일 결과 (결정론적 생성, add_watermark=false 필요)
    seed: Optional[int] = Field(None, ge=1, le=2147483647)
    # 프롬프트 충실도: 높을수록 프롬프트에 더 충실 (0~100)
    guidance_scale: Optional[int] = Field(None, ge=0, le=100)
    # 안전 필터 수준
    safety_filter_level: Optional[Literal[
        "block_low_and_above", "block_medium_and_above", "block_only_high"
    ]] = None
    # SynthID 디지털 워터마크 (기본 true, seed 사용 시 false 필요)
    add_watermark: Optional[bool] = None
    # 프롬프트 언어 설정
    language: Optional[Literal["auto", "en", "ko", "ja", "zh", "zh-CN", "zh-TW", "hi", "pt", "es"]] = None


class VideoGenerateRequest(BaseModel):
    """Text-to-Video 요청 — Veo 3.0 파라미터 (Vertex AI Docs 기반)"""
    prompt: str
    model: str

    # 화면 비율
    aspect_ratio: Optional[Literal["16:9", "9:16"]] = None
    # 영상 길이(초): Veo 3.0은 4, 6, 8초 지원
    duration_seconds: Optional[Literal[4, 6, 8]] = None
    # 네거티브 프롬프트
    negative_prompt: Optional[str] = None
    # 시드: 동일 값 → 동일 결과 (결정론적 생성)
    seed: Optional[int] = Field(None, ge=0, le=4294967295)
    # 오디오 동시 생성 (Veo 3.0 전용)
    generate_audio: Optional[bool] = None
    # 출력 해상도
    resolution: Optional[Literal["720p", "1080p"]] = None


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

async def process_image_generation(job_id: str, prompt: str, model: str, options: dict = None):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_image(prompt, job_id, options=options)
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

async def process_video_from_text(job_id: str, prompt: str, model: str, options: dict = None):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_video_from_text(prompt, job_id, options=options)
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

async def process_video_from_image(job_id: str, prompt: str, model: str, image_bytes: bytes, mime_type: str, options: dict = None):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_video_from_image(prompt, image_bytes, job_id, mime_type, options=options)
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
async def text_to_image(request: ImageGenerateRequest, background_tasks: BackgroundTasks):
    # Vertex AI 옵션 추출 (prompt, model 제외, None 값 제외)
    options = request.model_dump(exclude={"prompt", "model"}, exclude_none=True)

    # 캐시 확인: 고급 옵션이 없을 때만 캐시 조회 (옵션이 다르면 결과도 다름)
    if not options:
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

    # 캐시 미스 또는 고급 옵션 사용: 새로 생성
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    background_tasks.add_task(process_image_generation, job_id, request.prompt, request.model, options)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.post("/text-to-video", response_model=GenerateResponse)
async def text_to_video(request: VideoGenerateRequest, background_tasks: BackgroundTasks):
    options = request.model_dump(exclude={"prompt", "model"}, exclude_none=True)

    # 캐시 확인: 고급 옵션이 없을 때만
    if not options:
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

    # 캐시 미스 또는 고급 옵션 사용
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    background_tasks.add_task(process_video_from_text, job_id, request.prompt, request.model, options)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.post("/image-to-video", response_model=GenerateResponse)
async def image_to_video(
    prompt: str = Form(...),
    model: str = Form(...),
    image: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    # Veo 3.0 Image-to-Video 파라미터 (Vertex AI Docs 기반)
    duration_seconds: Optional[int] = Form(None),
    seed: Optional[int] = Form(None),
    resolution: Optional[str] = Form(None),
    resize_mode: Optional[str] = Form(None),
):
    # 옵션 딕셔너리 구성
    options = {}
    if duration_seconds is not None:
        options["duration_seconds"] = duration_seconds
    if seed is not None:
        options["seed"] = seed
    if resolution is not None:
        options["resolution"] = resolution
    if resize_mode is not None:
        options["resize_mode"] = resize_mode

    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    image_bytes = await image.read()
    mime_type = image.content_type or "image/png"
    background_tasks.add_task(process_video_from_image, job_id, prompt, model, image_bytes, mime_type, options)
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
