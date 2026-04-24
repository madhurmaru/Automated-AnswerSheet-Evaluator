import re


def clean_text(text: str) -> str:
    return "\n".join(" ".join(line.split()) for line in (text or "").splitlines() if line.strip())


def split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def join_keywords(items: list[str]) -> str:
    seen: list[str] = []
    for i in items:
        v = i.strip()
        if v and v not in seen:
            seen.append(v)
    return ",".join(seen)


def segment_by_question(text: str) -> dict[str, str]:
    pattern = re.compile(r"(?im)^\s*(?:q(?:uestion)?\s*)?(\d{1,2}|[il|])\s*[\.)\-:]\s*")
    source = text or ""
    source = re.sub(r"(?im)^\s*q\s*[il|]\b", "Q1", source)
    source = re.sub(r"(?im)^\s*[il|]\s*[\.)]", "1. ", source)

    matches = list(pattern.finditer(source))
    if not matches:
        return {"1": clean_text(source)} if source.strip() else {}

    out: dict[str, str] = {}
    for idx, m in enumerate(matches):
        q = m.group(1).replace("I", "1").replace("l", "1").replace("|", "1")
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source)
        ans = clean_text(source[start:end])
        if ans:
            out[str(int(q)) if q.isdigit() else "1"] = ans
    return out


def parse_marking_scheme(text: str) -> list[dict]:
    block_pattern = re.compile(r"(?ims)^\s*Q(\d{1,2})\s*[\.:\)]\s*(.+?)(?=^\s*Q\d{1,2}\s*[\.:\)]|\Z)")
    mark_pattern = re.compile(r"(?i)(\d+(?:\.\d+)?)\s*marks?")
    model_pattern = re.compile(r"(?is)model\s*answer\s*:\s*(.+?)(?=\n\s*(?:keywords?|key\s*steps?|marking\s*logic|$))")
    kw_pattern = re.compile(r"(?is)(?:keywords?\s*/\s*concepts?|key\s*steps?)\s*:\s*(.+?)(?=\n\s*(?:marking\s*logic|criteria/?step|$))")

    items: list[dict] = []
    for m in block_pattern.finditer(text or ""):
        q_num = m.group(1)
        block = m.group(2).strip()

        first_line = block.splitlines()[0] if block.splitlines() else f"Question {q_num}"
        marks_match = mark_pattern.search(first_line)
        max_marks = float(marks_match.group(1)) if marks_match else 10.0
        prompt = mark_pattern.sub("", first_line)
        prompt = re.sub(r"\(\s*\)", "", prompt).strip(" -:") or f"Question {q_num}"

        mm = model_pattern.search(block)
        rubric_text = clean_text(mm.group(1)) if mm else clean_text(block)

        kwm = kw_pattern.search(block)
        keywords: list[str] = []
        if kwm:
            for line in kwm.group(1).splitlines():
                v = line.strip().lstrip("•*-")
                if v:
                    if v.lower() in {"criteria/step", "criteria", "step", "marks"}:
                        continue
                    if re.fullmatch(r"\d+(?:\.\d+)?", v):
                        continue
                    keywords.append(v)

        items.append(
            {
                "question_number": q_num,
                "prompt": prompt,
                "max_marks": max_marks,
                "rubric_text": rubric_text,
                "keywords": keywords,
            }
        )

    return items
