# Silveri Hire - AI Hiring Platform

An AI-powered, multi-tenant hiring platform that automates resume screening, conducts live voice interviews using Google Gemini AI, and manages the full recruitment pipeline from intake to hire.

## Technology Stack

| Layer      | Technology                            |
| ---------- | ------------------------------------- |
| Backend    | Python, FastAPI, Uvicorn              |
| Frontend   | React 19, Vite 6, react-router-dom 7  |
| Database   | MongoDB (pymongo)                     |
| AI         | Google Gemini API (REST + Live voice) |
| Email      | Brevo API / SMTP                      |
| Storage    | Cloudflare R2 (interview recordings)  |
| Auth       | JWT (HS256) + bcrypt                  |
| Deployment | Docker, Render.com                    |

## Main Features

- **Multi-Tenant SaaS** — Company-level data isolation with plan-based seat and credit limits.
- **AI Resume Parsing** — Extracts structured candidate data from PDF, DOCX, TXT, and scanned images (Gemini OCR).
- **AI Resume Screening** — Scores candidates against job requirements on 5 weighted dimensions.
- **Live AI Voice Interviews** — Real-time conversational interviews via Gemini Live API with HR and Technical round personas.
- **Custom Coding Questions** — Upload question banks for the technical round; candidates type answers in-interview.
- **Browser Proctoring** — Fullscreen enforcement with 2-strike tab-switching detection.
- **Interview Recording** — Full video + audio recording uploaded to Cloudflare R2.
- **Hiring Pipeline** — Multi-stage pipeline (Screening → HR → Technical) with admin override capability.
- **Credit System** — Cumulative 10-minute block billing with atomic deductions.
- **Email Notifications** — Automated invitation, credential, and hire notification emails via Brevo.
- **Audit Logging** — Every mutation tracked with actor, IP, and metadata.
- **Team Management** — Granular permission system for sub-users (6 permission types).
- **Lead Capture** — Public demo request form with server-side CAPTCHA and admin CRM panel.

## Quick Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB
- Google Gemini API key

### Installation

```bash
# Clone and configure
git clone <repository-url>
cd AI_Hiring
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
pip install -r requirements.txt
cd frontend && npm install && cd ..

# Build frontend and start
cd frontend && npm run build && cd ..
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The application runs at `http://localhost:8000`.

### Docker

```bash
docker build -t hireai .
docker run -p 8000:8000 --env-file .env hireai
```

### Environment Variables

Copy `.env.example` and configure at minimum:

| Variable                 | Purpose                               |
| ------------------------ | ------------------------------------- |
| `GEMINI_API_KEY`       | Google Gemini API key                 |
| `MONGODB_URI`          | MongoDB connection string             |
| `JWT_SECRET`           | JWT signing secret                    |
| `SUPER_ADMIN_EMAIL`    | Platform admin email                  |
| `SUPER_ADMIN_PASSWORD` | Platform admin password               |
| `FRONTEND_URL`         | Public frontend URL (for email links) |

See `.env.example` for the complete list of configuration options.

## Project Structure

```
AI_Hiring/
├── backend/
│   ├── main.py              # FastAPI app entry point
│   ├── auth/                # Authentication & authorization
│   ├── admin/               # Super Admin & Company Admin routes
│   ├── core/                # Data models & sanitization
│   ├── live/                # Gemini Live API relay
│   ├── leads/               # Public lead capture
│   ├── services/            # AI ranking, parsing, email, OCR
│   │   ├── Technical/       # Technical interview prompts & evaluator
│   │   └── HR_Round/        # HR interview prompts & evaluator
│   └── storage/             # MongoDB persistence layer
├── frontend/
│   └── src/
│       ├── main.jsx         # App entry & routing
│       ├── components/      # React components (14 modules)
│       ├── hooks/           # Custom hooks (auth, proctoring, upload)
│       └── utils/           # API client, CSV, pipeline status
├── docs/
│   └── HANDOVER.md          # Full technical handover documentation
├── tests/                   # Integration & unit tests
├── Dockerfile               # Multi-stage Docker build
├── render.yaml              # Render.com deployment config
├── requirements.txt         # Python dependencies
└── .env.example             # Environment variable template
```

## Documentation

For complete technical documentation, architecture details, feature explanations, database schema, API reference, and deployment instructions, see:

📄 **[docs/HANDOVER.md](docs/HANDOVER.md)**

## User Roles

| Role                    | Description                                                       |
| ----------------------- | ----------------------------------------------------------------- |
| **Super Admin**   | Platform owner. Manages companies, plans, credits, and leads.     |
| **Company Admin** | Organization owner. Manages hiring drives, team, and pipeline.    |
| **Sub-User**      | HR/Recruiter with granular permissions assigned by Company Admin. |
| **Candidate**     | Accesses interviews via tokenized links. No login required.       |

## License

Proprietary. All rights reserved.
