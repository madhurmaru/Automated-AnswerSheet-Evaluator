from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AnswerSheet Evaluator (Minimal)"
    api_prefix: str = "/api"
    secret_key: str = "change-this"
    database_url: str = "sqlite:///./app.db"
    upload_dir: str = "../uploads"
    access_token_expire_minutes: int = 1440

    default_admin_username: str = "teacher"
    default_admin_password: str = "teacher123"

    ocr_api_url: str = "https://api.ocr.space/parse/image"
    ocr_api_key: str = ""
    ocr_language: str = "eng"
    ocr_engine: int = 2

    hf_api_url: str = "https://router.huggingface.co/v1/chat/completions"
    hf_api_key: str = ""
    hf_model: str = "openai/gpt-oss-20b:fireworks-ai"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def upload_path(self) -> Path:
        return Path(self.upload_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
