from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_teacher = Column(Boolean, default=True)


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_paper_path = Column(String(500), nullable=True)
    marking_scheme_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    sheets = relationship("AnswerSheet", back_populates="exam", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    question_number = Column(String(20), nullable=False)
    prompt = Column(Text, nullable=False)
    rubric_text = Column(Text, nullable=False)
    max_marks = Column(Float, nullable=False)
    keywords = Column(Text, nullable=True)

    exam = relationship("Exam", back_populates="questions")


class AnswerSheet(Base):
    __tablename__ = "answer_sheets"

    id = Column(Integer, primary_key=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    student_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    extracted_text = Column(Text, nullable=True)
    ocr_status = Column(String(50), default="pending")
    ocr_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    exam = relationship("Exam", back_populates="sheets")
    segments = relationship("AnswerSegment", back_populates="sheet", cascade="all, delete-orphan")
    results = relationship("EvaluationResult", back_populates="sheet", cascade="all, delete-orphan")


class AnswerSegment(Base):
    __tablename__ = "answer_segments"

    id = Column(Integer, primary_key=True)
    sheet_id = Column(Integer, ForeignKey("answer_sheets.id"), nullable=False)
    question_number = Column(String(20), nullable=False)
    answer_text = Column(Text, nullable=False)

    sheet = relationship("AnswerSheet", back_populates="segments")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id = Column(Integer, primary_key=True)
    sheet_id = Column(Integer, ForeignKey("answer_sheets.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    awarded_marks = Column(Float, nullable=False)
    feedback = Column(Text, nullable=True)
    semantic_similarity = Column(Float, nullable=True)
    keyword_coverage = Column(Float, nullable=True)
    completeness = Column(Float, nullable=True)
    llm_raw = Column(Text, nullable=True)

    sheet = relationship("AnswerSheet", back_populates="results")
