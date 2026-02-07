from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    google_cloud_project: str = ""
    google_cloud_region: str = "us-central1"
    storage_path: str = "/app/storage"

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()
