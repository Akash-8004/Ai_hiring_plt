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
- Invite shortlisted candidates to AI technical/HR interviews via link
- **Live voice AI interview** — Gemini Live via a FastAPI WebSocket relay (browser mic/audio ↔ server-side Gemini Live session)
- Auto-evaluation when the AI interviewer ends the conversation; transcript persisted to MongoDB as it happens

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

The file `backend/services/ai_ranker.py` contains `AIRankingService`.

The React app calls FastAPI endpoints under `backend/main.py`:

- `GET /api/workspace`
- `PUT /api/job`
- `POST /api/resumes/upload`
- `POST /api/resumes/manual`
- `POST /api/resumes/sample`
- `DELETE /api/resumes`
- `POST /api/candidates/{email}/invite`
- `GET /api/interview/session/{token}`
- `POST /api/interview/evaluate`
- `WS /ws/interview/{token}` (Gemini Live relay)

## Live Voice Interview (Gemini Live)

The conversation uses the **Gemini Live API** over a server-side WebSocket relay so
the API key never reaches the browser:

```
Browser mic ──(AudioWorklet → 16kHz PCM)──▶ FastAPI /ws/interview/{token} ──▶ Gemini Live
Browser speakers ◀──(PCM audio + transcript)── FastAPI ◀── audio + STT/TTS ──┘
```

- `backend/live/relay.py` — `GeminiLiveRelay` wraps `google-genai`'s `client.aio.live.connect()`.
- Frontend mic capture/playback lives in `frontend/src/components/interview/liveClient.js`.
- Transcription is enabled in both directions (`input_audio_transcription` / `output_audio_transcription`);
  each finished turn is appended to the candidate document in Mongo, so nothing is lost if the tab closes.
- When the interviewer says the closing phrase ("The interview is now complete."), the backend
  automatically evaluates the transcript and closes the session. The candidate can also click
  "End Interview" to evaluate early.

Configure in `.env`:

```env
GEMINI_LIVE_MODEL=gemini-3.1-flash-live-preview
GEMINI_LIVE_VOICE=Puck
```

## Project Structure

```text
backend/
  main.py                 # FastAPI app: routes + live WebSocket relay wiring
  config.py               # loads .env once for every module
  core/                   # shared data models + seed data
  services/               # business logic (ranking, parsing, interviews, prompts)
  storage/                # MongoDB persistence layer
  live/                   # Gemini Live relay (server-side API key)
frontend/
  src/
    main.jsx              # app entry; routes views and the interview page
    components/
      layout/             # Sidebar, Topbar
      dashboard/          # Dashboard + candidate table
      job/                # Job setup editor
      resumes/            # Resume intake
      pipeline/           # Pipeline + candidate rows
      candidate/          # Candidate detail panel
      settings/           # Settings view
      interview/          # Live voice interview UI + WebSocket client
      common/             # shared UI primitives (Field, Metric, StatusBadge, ...)
```

## Suggested Next Phases

1. Replace in-memory state with PostgreSQL tables from the TDD.
2. Add real PDF/DOCX extraction libraries for production parsing.
3. Move ranking to FastAPI background jobs.
4. Add company authentication and tenant isolation.
5. Add session resumption for Live sessions longer than the ~10 minute connection limit.
