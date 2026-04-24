from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings


class StorageService:
    def __init__(self) -> None:
        self.base = get_settings().upload_path
        self.base.mkdir(parents=True, exist_ok=True)

    def save(self, exam_id: int, file: UploadFile, label: str) -> Path:
        exam_dir = self.base / f"exam_{exam_id}"
        exam_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(file.filename or "upload.bin").suffix or ".bin"
        target = exam_dir / f"{label}_{uuid4().hex}{suffix}"
        with target.open("wb") as out:
            out.write(file.file.read())
        return target
