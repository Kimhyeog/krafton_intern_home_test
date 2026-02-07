from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db import connect_db, disconnect_db
from app.routers import generate, assets, auth
from app.config import get_settings
import os

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(os.path.join(settings.storage_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(settings.storage_path, "videos"), exist_ok=True)
    await connect_db()
    yield
    await disconnect_db()

app = FastAPI(title="Vertex AI Asset Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=settings.storage_path), name="storage")
app.include_router(auth.router)
app.include_router(generate.router)
app.include_router(assets.router)

@app.get("/health")
async def health():
    return {"status": "healthy"}
