from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    database_url: str
    google_cloud_project: str = ""
    google_cloud_region: str = "us-central1"
    storage_path: str = "/app/storage"

    # JWT 인증 설정
    jwt_secret_key: str = "krafton-jwt-default-dev-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    model_config = SettingsConfigDict(env_file=".env")

@lru_cache
def get_settings():
    return Settings()
