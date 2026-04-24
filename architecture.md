# Minimal Architecture

## Modules
- FastAPI backend (`backend/app`) for auth, exam setup, OCR ingestion, and LLM evaluation.
- Simple frontend (`frontend/index.html + app.js`) for teacher workflow.
- SQLite DB for users, exams, questions, answer sheets, segments, and results.

## Flow
1. Teacher logs in.
2. Teacher creates exam.
3. Teacher uploads question paper.
4. Teacher uploads marking scheme.
5. Backend OCRs marking scheme and auto-creates question rubrics.
6. Teacher uploads answer sheets one by one.
7. Backend OCRs sheet, segments answers by question number.
8. Hugging Face LLM API evaluates each answer with rubric + keywords.

## APIs Used
- OCR API (OCR.space by default)
- Hugging Face LLM API (chat completion endpoint)
