import mimetypes
import subprocess
from pathlib import Path

import httpx

from app.core.config import get_settings
from app.utils.text import clean_text


class OCRApiService:
    def __init__(self) -> None:
        s = get_settings()
        self.url = s.ocr_api_url
        self.key = s.ocr_api_key
        self.language = s.ocr_language
        self.engine = s.ocr_engine

    def extract(self, file_path: Path) -> tuple[str, float | None]:
        if not self.key:
            # Allow local fallback for text-based PDFs during demo runs.
            fallback = self._local_pdf_text(file_path)
            if fallback:
                return fallback, 0.8
            raise ValueError("OCR_API_KEY is missing in backend/.env")

        mime, _ = mimetypes.guess_type(str(file_path))
        mime = mime or "application/octet-stream"

        try:
            with file_path.open("rb") as fh:
                files = {"file": (file_path.name, fh, mime)}
                data = {
                    "apikey": self.key,
                    "language": self.language,
                    "OCREngine": str(self.engine),
                    "isOverlayRequired": "true",
                    "detectOrientation": "true",
                    "scale": "true",
                }
                r = httpx.post(self.url, data=data, files=files, timeout=120.0)
                r.raise_for_status()
                payload = r.json()
        except Exception as exc:
            fallback = self._local_pdf_text(file_path)
            if fallback:
                return fallback, 0.75
            raise RuntimeError(f"OCR API request failed: {exc}") from exc

        if payload.get("IsErroredOnProcessing"):
            errors = payload.get("ErrorMessage") or payload.get("ErrorDetails") or ["OCR failed"]
            fallback = self._local_pdf_text(file_path)
            if fallback:
                return fallback, 0.75
            raise RuntimeError("; ".join(errors if isinstance(errors, list) else [str(errors)]))

        text_parts = []
        for item in payload.get("ParsedResults", []):
            parsed = (item or {}).get("ParsedText", "")
            if parsed.strip():
                text_parts.append(parsed.strip())

        text = clean_text("\n".join(text_parts))
        conf = None
        if text:
            alpha = sum(1 for ch in text if ch.isalpha())
            conf = min(0.95, max(0.35, alpha / max(len(text), 1)))
        return text, conf

    def _local_pdf_text(self, file_path: Path) -> str:
        if file_path.suffix.lower() != ".pdf":
            return ""
        try:
            out = subprocess.check_output(["pdftotext", str(file_path), "-"], stderr=subprocess.DEVNULL)
            text = clean_text(out.decode("utf-8", errors="ignore"))
            return text
        except Exception:
            return ""
