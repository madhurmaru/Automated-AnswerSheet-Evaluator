import json
from typing import Any

import httpx

from app.core.config import get_settings


class HuggingFaceEvaluator:
    def __init__(self) -> None:
        s = get_settings()
        self.url = s.hf_api_url
        self.key = s.hf_api_key
        self.model = s.hf_model

    def evaluate(self, question: str, rubric: str, keywords: list[str], student_answer: str, max_marks: float) -> dict[str, Any]:
        if not self.key:
            return self._fallback(keywords, student_answer, max_marks, "HF_API_KEY missing, used fallback")

        prompt = f"""
You are grading one answer.
Return ONLY valid JSON with keys:
semantic_similarity (0..1), keyword_coverage (0..1), completeness (0..1), awarded_marks (0..{max_marks}), feedback.

Question: {question}
Rubric: {rubric}
Keywords: {', '.join(keywords) if keywords else 'None'}
Student Answer: {student_answer}
""".strip()

        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a strict but fair exam evaluator."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }

        try:
            r = httpx.post(self.url, headers=headers, json=payload, timeout=90.0)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            result = self._parse_json(content)
            result["llm_raw"] = content
            return self._sanitize(result, max_marks)
        except Exception as exc:
            return self._fallback(keywords, student_answer, max_marks, f"HF failed: {exc}")

    def parse_marking_scheme(self, raw_text: str) -> list[dict[str, Any]]:
        """
        Parse OCR text of a marking scheme into structured question objects using LLM.
        Returns empty list when API key/model call fails so caller can fallback safely.
        """
        if not self.key:
            return []

        prompt = f"""
Extract question-wise marking scheme from the text below.
Return ONLY valid JSON as an array of objects with keys:
question_number (string),
prompt (string),
max_marks (number),
rubric_text (string),
keywords (array of strings).

Rules:
- Include only real question entries (Q1, Q2, ...).
- Ignore global scoring formulas and generic notes.
- Keep prompt concise and clean.
- Keep keywords meaningful and deduplicated.
- max_marks must be numeric.

Text:
{raw_text}
""".strip()

        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a precise parser that outputs strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
        }

        try:
            r = httpx.post(self.url, headers=headers, json=payload, timeout=90.0)
            r.raise_for_status()
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            parsed = self._parse_json(content)

            if not isinstance(parsed, list):
                return []

            normalized: list[dict[str, Any]] = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue

                qn = str(item.get("question_number", "")).strip()
                if not qn:
                    continue
                if qn.lower().startswith("q"):
                    qn = qn[1:].strip()

                prompt_value = str(item.get("prompt", "")).strip() or f"Question {qn}"
                rubric = str(item.get("rubric_text", "")).strip()
                if not rubric:
                    continue

                try:
                    max_marks = float(item.get("max_marks", 0))
                except Exception:
                    max_marks = 0.0
                if max_marks <= 0:
                    max_marks = 10.0

                raw_keywords = item.get("keywords", [])
                if isinstance(raw_keywords, list):
                    keywords = [str(k).strip() for k in raw_keywords if str(k).strip()]
                else:
                    keywords = []

                dedup_keywords: list[str] = []
                seen = set()
                for k in keywords:
                    lk = k.lower()
                    if lk not in seen:
                        seen.add(lk)
                        dedup_keywords.append(k)

                normalized.append(
                    {
                        "question_number": qn,
                        "prompt": prompt_value,
                        "max_marks": max_marks,
                        "rubric_text": rubric,
                        "keywords": dedup_keywords,
                    }
                )
            return normalized
        except Exception:
            return []

    def _parse_json(self, text: str) -> dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        return json.loads(text)

    def _sanitize(self, result: dict[str, Any], max_marks: float) -> dict[str, Any]:
        semantic = float(result.get("semantic_similarity", 0.0))
        keyword = float(result.get("keyword_coverage", 0.0))
        completeness = float(result.get("completeness", 0.0))
        awarded = float(result.get("awarded_marks", 0.0))

        semantic = max(0.0, min(1.0, semantic))
        keyword = max(0.0, min(1.0, keyword))
        completeness = max(0.0, min(1.0, completeness))
        awarded = max(0.0, min(max_marks, awarded))

        return {
            "semantic_similarity": semantic,
            "keyword_coverage": keyword,
            "completeness": completeness,
            "awarded_marks": round(awarded, 2),
            "feedback": str(result.get("feedback", "")),
            "llm_raw": result.get("llm_raw", ""),
        }

    def _fallback(self, keywords: list[str], student_answer: str, max_marks: float, note: str) -> dict[str, Any]:
        student_lower = student_answer.lower()
        if keywords:
            matched = sum(1 for k in keywords if k.lower() in student_lower)
            keyword_coverage = matched / len(keywords)
        else:
            keyword_coverage = 0.5 if student_answer.strip() else 0.0

        completeness = min(1.0, len(student_answer.split()) / 60)
        semantic = (0.6 * keyword_coverage) + (0.4 * completeness)
        score = (0.5 * semantic) + (0.3 * keyword_coverage) + (0.2 * completeness)

        return {
            "semantic_similarity": round(semantic, 3),
            "keyword_coverage": round(keyword_coverage, 3),
            "completeness": round(completeness, 3),
            "awarded_marks": round(score * max_marks, 2),
            "feedback": f"Auto-evaluated (fallback). {note}",
            "llm_raw": note,
        }
