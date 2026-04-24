# AnswerSheet Evaluator (Minimal)

A simple project from scratch with minimal features:
- Teacher login
- Create exam/assessment
- Upload question paper
- Upload marking scheme
- Upload answer sheets one by one
- OCR extraction using OCR API
- Evaluation using Hugging Face LLM API

## Folder Structure
```text
answersheet evaluator/
  backend/
    app/
      api/routes.py
      core/
      services/
      utils/
      models.py
      main.py
    requirements.txt
    .env.example
    seed.py
  frontend/
    index.html
    app.js
    styles.css
  uploads/
  docs/
    architecture.md
```

## 1. Backend Setup
```bash
cd "/Users/madhur/Desktop/NLP/answersheet evaluator/backend"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Update `backend/.env` with your keys:
```env
OCR_API_KEY=your_ocr_space_key
HF_API_KEY=your_huggingface_key
```

Run backend:
```bash
python seed.py
uvicorn app.main:app --reload --port 8000
```

Default login:
- username: `teacher`
- password: `teacher123`

## 2. Frontend Run
Use any simple static server:
```bash
cd "/Users/madhur/Desktop/NLP/answersheet evaluator/frontend"
python3 -m http.server 5173
```

Open: `http://localhost:5173`

## 3. Workflow
1. Login
2. Create exam
3. Upload question paper
4. Upload marking scheme
5. Upload answer sheets
6. Click Evaluate per sheet

## Notes
- Keep marking scheme in `Q1/Q2` style with `Model Answer:` for best parsing.
- If HF API fails, backend uses a simple fallback scoring heuristic.
