from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from jose import JWTError, jwt
from openpyxl import Workbook
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import io

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_token, hash_password, verify_password
from app.models import AnswerSegment, AnswerSheet, EvaluationResult, Exam, Question, User
from app.services.hf_evaluator import HuggingFaceEvaluator
from app.services.ocr_api import OCRApiService
from app.services.storage import StorageService
from app.utils.text import join_keywords, parse_marking_scheme, segment_by_question, split_keywords

router = APIRouter()
settings = get_settings()
storage = StorageService()
ocr_service = OCRApiService()
hf_evaluator = HuggingFaceEvaluator()


def get_current_user(authorization: Annotated[str | None, Header()] = None, db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/login")
def login(payload: dict, db: Session = Depends(get_db)):
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_token(user.username), "token_type": "bearer"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username}


@router.post("/exams")
def create_exam(payload: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    exam = Exam(title=title, created_by=user.id)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return {"id": exam.id, "title": exam.title}


@router.get("/exams")
def list_exams(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exams = db.query(Exam).order_by(Exam.created_at.desc()).all()
    return [{"id": e.id, "title": e.title, "question_paper": bool(e.question_paper_path), "marking_scheme": bool(e.marking_scheme_path)} for e in exams]


@router.get("/exams/{exam_id}")
def get_exam(exam_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).order_by(Question.question_number.asc()).all()
    return {
        "id": exam.id,
        "title": exam.title,
        "question_paper_path": exam.question_paper_path,
        "marking_scheme_path": exam.marking_scheme_path,
        "questions": [
            {
                "id": q.id,
                "question_number": q.question_number,
                "prompt": q.prompt,
                "max_marks": q.max_marks,
                "keywords": split_keywords(q.keywords),
                "rubric_text": q.rubric_text,
            }
            for q in questions
        ],
    }


@router.post("/exams/{exam_id}/question-paper")
def upload_question_paper(
    exam_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    path = storage.save(exam_id, file, "question_paper")
    exam.question_paper_path = str(path)
    db.commit()
    return {"ok": True, "question_paper_path": exam.question_paper_path}


@router.post("/exams/{exam_id}/marking-scheme")
def upload_marking_scheme(
    exam_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    path = storage.save(exam_id, file, "marking_scheme")
    exam.marking_scheme_path = str(path)

    try:
        text, conf = ocr_service.extract(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"OCR provider error: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR failed: {exc}") from exc

    parsed = hf_evaluator.parse_marking_scheme(text)
    parse_source = "llm"
    if not parsed:
        parsed = parse_marking_scheme(text)
        parse_source = "regex-fallback"
    if not parsed:
        raise HTTPException(status_code=400, detail="Could not parse marking scheme. Use Q1/Q2 format with Model Answer.")

    db.query(Question).filter(Question.exam_id == exam_id).delete()
    for item in parsed:
        db.add(
            Question(
                exam_id=exam_id,
                question_number=item["question_number"],
                prompt=item["prompt"],
                rubric_text=item["rubric_text"],
                max_marks=item["max_marks"],
                keywords=join_keywords(item["keywords"]),
            )
        )

    db.commit()
    return {"ok": True, "parsed_questions": len(parsed), "ocr_confidence": conf, "parse_source": parse_source}


@router.post("/exams/{exam_id}/answersheets")
def upload_answersheet(
    exam_id: int,
    student_name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    path = storage.save(exam_id, file, "answersheet")
    sheet = AnswerSheet(exam_id=exam_id, student_name=student_name, file_path=str(path), ocr_status="processing")
    db.add(sheet)
    db.commit()
    db.refresh(sheet)

    try:
        text, conf = ocr_service.extract(path)
        sheet.extracted_text = text
        sheet.ocr_confidence = conf
        sheet.ocr_status = "completed" if text.strip() else "low_quality"

        db.query(AnswerSegment).filter(AnswerSegment.sheet_id == sheet.id).delete()
        for q_num, ans in segment_by_question(text).items():
            db.add(AnswerSegment(sheet_id=sheet.id, question_number=q_num, answer_text=ans))
        db.commit()
    except ValueError as exc:
        sheet.ocr_status = "failed"
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        sheet.ocr_status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"OCR provider error: {exc}") from exc
    except Exception as exc:
        sheet.ocr_status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Answer sheet OCR failed: {exc}") from exc

    db.refresh(sheet)
    return {
        "id": sheet.id,
        "student_name": sheet.student_name,
        "ocr_status": sheet.ocr_status,
        "ocr_confidence": sheet.ocr_confidence,
    }


@router.get("/exams/{exam_id}/answersheets")
def list_answersheets(exam_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(AnswerSheet).filter(AnswerSheet.exam_id == exam_id).order_by(AnswerSheet.created_at.desc()).all()
    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    max_total = round(sum(float(q.max_marks or 0) for q in questions), 2)
    return [
        {
            "id": s.id,
            "student_name": s.student_name,
            "ocr_status": s.ocr_status,
            "ocr_confidence": s.ocr_confidence,
            "created_at": s.created_at,
            "total_score": round(sum(float(r.awarded_marks or 0) for r in s.results), 2),
            "max_total": max_total,
            "evaluated": len(s.results) > 0,
        }
        for s in rows
    ]


@router.delete("/answersheets/{sheet_id}")
def delete_answersheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sheet = db.query(AnswerSheet).filter(AnswerSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Answer sheet not found")
    db.delete(sheet)
    db.commit()
    return {"ok": True, "deleted_sheet_id": sheet_id}


@router.get("/exams/{exam_id}/answersheets/export-excel")
def export_answersheets_excel(exam_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    questions = db.query(Question).filter(Question.exam_id == exam_id).all()
    max_total = round(sum(float(q.max_marks or 0) for q in questions), 2)
    sheets = db.query(AnswerSheet).filter(AnswerSheet.exam_id == exam_id).order_by(AnswerSheet.created_at.desc()).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "AnswerSheets"
    ws.append(["Sheet ID", "Student Name", "OCR Status", "OCR Confidence", "Score", "Max Score", "Evaluated"])

    for s in sheets:
        total_score = round(sum(float(r.awarded_marks or 0) for r in s.results), 2)
        ws.append(
            [
                s.id,
                s.student_name,
                s.ocr_status,
                float(s.ocr_confidence) if s.ocr_confidence is not None else "",
                total_score,
                max_total,
                "Yes" if len(s.results) > 0 else "No",
            ]
        )

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    filename = f"exam_{exam_id}_answersheets.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/answersheets/{sheet_id}/evaluate")
def evaluate_sheet(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sheet = db.query(AnswerSheet).filter(AnswerSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Answer sheet not found")

    questions = db.query(Question).filter(Question.exam_id == sheet.exam_id).order_by(Question.question_number.asc()).all()
    if not questions:
        raise HTTPException(status_code=400, detail="No questions found. Upload marking scheme first.")

    seg_map = {seg.question_number: seg.answer_text for seg in sheet.segments}

    db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).delete()

    total = 0.0
    created = []
    for q in questions:
        student_answer = seg_map.get(q.question_number, "")
        res = hf_evaluator.evaluate(
            question=q.prompt,
            rubric=q.rubric_text,
            keywords=split_keywords(q.keywords),
            student_answer=student_answer,
            max_marks=q.max_marks,
        )

        row = EvaluationResult(
            sheet_id=sheet.id,
            question_id=q.id,
            awarded_marks=res["awarded_marks"],
            feedback=res.get("feedback", ""),
            semantic_similarity=res.get("semantic_similarity"),
            keyword_coverage=res.get("keyword_coverage"),
            completeness=res.get("completeness"),
            llm_raw=res.get("llm_raw", ""),
        )
        db.add(row)
        total += row.awarded_marks
        created.append((q, row, student_answer))

    db.commit()

    return {
        "sheet_id": sheet.id,
        "student_name": sheet.student_name,
        "total_marks": round(total, 2),
        "results": [
            {
                "question_number": q.question_number,
                "question": q.prompt,
                "student_answer": ans,
                "rubric": q.rubric_text,
                "awarded_marks": r.awarded_marks,
                "max_marks": q.max_marks,
                "semantic_similarity": r.semantic_similarity,
                "keyword_coverage": r.keyword_coverage,
                "completeness": r.completeness,
                "feedback": r.feedback,
            }
            for q, r, ans in created
        ],
    }


@router.get("/answersheets/{sheet_id}/results")
def get_results(sheet_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    sheet = db.query(AnswerSheet).filter(AnswerSheet.id == sheet_id).first()
    if not sheet:
        raise HTTPException(status_code=404, detail="Answer sheet not found")

    results = db.query(EvaluationResult).filter(EvaluationResult.sheet_id == sheet_id).all()
    qmap = {q.id: q for q in db.query(Question).filter(Question.exam_id == sheet.exam_id).all()}

    total = 0.0
    out = []
    for r in results:
        q = qmap.get(r.question_id)
        if not q:
            continue
        total += r.awarded_marks
        out.append(
            {
                "question_number": q.question_number,
                "question": q.prompt,
                "awarded_marks": r.awarded_marks,
                "max_marks": q.max_marks,
                "feedback": r.feedback,
            }
        )

    return {"sheet_id": sheet.id, "student_name": sheet.student_name, "total_marks": round(total, 2), "results": out}


@router.post("/seed")
def seed(db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == settings.default_admin_username).first()
    if existing:
        return {"ok": True, "message": "Already seeded"}

    db.add(
        User(
            username=settings.default_admin_username,
            hashed_password=hash_password(settings.default_admin_password),
            is_teacher=True,
        )
    )
    db.commit()
    return {"ok": True, "username": settings.default_admin_username, "password": settings.default_admin_password}
