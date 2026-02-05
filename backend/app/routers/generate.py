from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
from uuid import uuid4
from datetime import datetime
from app.db import db
from app.services.job_manager import job_manager
from app.services.vertex_ai import vertex_ai_service

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

# ===== Background Tasks =====

async def process_image_generation(job_id: str, prompt: str, model: str):
    try:
        await job_manager.update_job(job_id, status="processing")
        result_url = await vertex_ai_service.generate_image(prompt, job_id)
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": prompt,
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
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": prompt,
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
        asset = await db.asset.create(data={
            "jobId": job_id,
            "filePath": result_url,
            "prompt": prompt,
            "model": model,
            "assetType": "video"
        })
        await job_manager.update_job(job_id, status="completed", asset_id=asset.id, result_url=result_url)
    except Exception as e:
        await job_manager.update_job(job_id, status="failed", error_message=str(e))

# ===== API Endpoints =====

@router.post("/text-to-image", response_model=GenerateResponse)
async def text_to_image(request: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid4())
    job = await job_manager.create_job(job_id)
    background_tasks.add_task(process_image_generation, job_id, request.prompt, request.model)
    return GenerateResponse(job_id=job_id, status="pending", created_at=job.created_at)

@router.post("/text-to-video", response_model=GenerateResponse)
async def text_to_video(request: GenerateRequest, background_tasks: BackgroundTasks):
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
