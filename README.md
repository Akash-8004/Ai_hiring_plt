# AI Hiring Platform SaaS Template

This is a runnable first template for the AI Hiring Platform described in `AI_Hiring_Platform_TDD (1).docx`.

Current scope:

- Modern React SaaS dashboard
- Python FastAPI backend
- Company/HR demo workspace
- Job description setup by HR
- Resume upload placeholder for TXT, PDF, and DOCX
- AI shortlisting placeholder with scoring dimensions
- Configurable shortlist threshold
- HR dashboard showing shortlisted and rejected candidates
- Export-ready candidate table

The AI interview and HR interview modules are intentionally left as future placeholders.

## Run Locally

Backend:

```powershell
python -m uvicorn backend.main:app --reload --port 8000
```

Frontend:

```powershell
cd frontend
cmd /c npm install
cmd /c npm run dev
```

Open:

```text
http://localhost:5173
```

If you move the project to another machine:

```powershell
pip install -r requirements.txt
cd frontend
cmd /c npm install
```

## Gemini Resume Screening

The current ranker uses Gemini first when these variables are available in `.env`:

```env
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key_here
```

Gemini returns a structured screening result with:

- total score
- shortlist recommendation
- matched skills
- missing skills
- dimension breakdown
- HR-facing summary

If Gemini is unavailable, the backend falls back to a deterministic local scoring technique so the dashboard still works:

- skill match
- keyword match
- experience match
- education signal
- semantic placeholder score

The file `src/ai_ranker.py` contains `AIRankingService`.

The React app calls FastAPI endpoints under `backend/main.py`:

- `GET /api/workspace`
- `PUT /api/job`
- `POST /api/resumes/upload`
- `POST /api/resumes/manual`
- `POST /api/resumes/sample`
- `DELETE /api/resumes`

## Suggested Next Phases

1. Replace in-memory state with PostgreSQL tables from the TDD.
2. Add real PDF/DOCX extraction libraries for production parsing.
3. Move ranking to FastAPI background jobs.
4. Add company authentication and tenant isolation.
5. Add AI interview scheduling, AI interview session, transcript, and evaluation modules.
