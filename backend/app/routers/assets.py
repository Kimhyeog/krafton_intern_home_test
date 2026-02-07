import os
from fastapi import APIRouter, HTTPException, Depends
from app.db import db
from app.services.auth import get_current_user
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("/")
async def list_assets(skip: int = 0, limit: int = 20, current_user=Depends(get_current_user)):
    """본인 에셋만 조회 (최신순)"""
    return await db.asset.find_many(
        where={"userId": current_user.id},
        skip=skip,
        take=limit,
        order={"createdAt": "desc"},
    )


@router.get("/{asset_id}")
async def get_asset(asset_id: int, current_user=Depends(get_current_user)):
    """본인 에셋만 상세 조회"""
    asset = await db.asset.find_first(where={"id": asset_id, "userId": current_user.id})
    if not asset:
        raise HTTPException(status_code=404, detail="에셋을 찾을 수 없습니다.")
    return asset


@router.delete("/{asset_id}")
async def delete_asset(asset_id: int, current_user=Depends(get_current_user)):
    """본인 에셋 삭제 (DB + 물리 파일)"""
    asset = await db.asset.find_first(where={"id": asset_id, "userId": current_user.id})
    if not asset:
        raise HTTPException(status_code=404, detail="에셋을 찾을 수 없습니다.")

    # 물리 파일 삭제
    if asset.filePath:
        relative_path = asset.filePath.lstrip("/storage/")
        file_path = os.path.join(settings.storage_path, relative_path)
        if os.path.exists(file_path):
            os.remove(file_path)

    # DB 레코드 삭제
    await db.asset.delete(where={"id": asset_id})
    return {"message": "삭제되었습니다."}
