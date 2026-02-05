from fastapi import APIRouter, HTTPException
from app.db import db

router = APIRouter(prefix="/api/assets", tags=["assets"])

@router.get("/{asset_id}")
async def get_asset(asset_id: int):
    asset = await db.asset.find_unique(where={"id": asset_id})
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset

@router.get("/")
async def list_assets(skip: int = 0, limit: int = 20):
    return await db.asset.find_many(
        skip=skip,
        take=limit,
        order={"createdAt": "desc"}
    )
