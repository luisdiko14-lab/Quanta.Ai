# Quanta AI

A multi-provider AI workspace built around FastAPI, React, PostgreSQL, Redis and Docker.

**Status:** Foundation, accounts and chat-history milestone. This branch includes the initial web application, provider configuration, database schema, guest sessions, email/password account endpoints, CSRF protection, persistent conversations for signed-in users, local Docker stack and CI. Billing, administration, uploads and remaining product modules are follow-on milestones and are not claimed as complete.

## Stack
- API: Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2, Alembic
- Web: React, TypeScript, Vite, Lucide
- Data: PostgreSQL and Redis
- AI: Gemini, Groq and DeepSeek, with server-side provider adapters
- Operations: Docker Compose, Nginx and GitHub Actions

## Run
1. Copy `.env.example` to `.env` and set a unique `SECRET_KEY`.
2. Configure provider keys and current model IDs in `.env`. Never add provider keys to frontend variables.
3. Run `docker compose up --build`.
4. Open `http://localhost:8080`; API health is at `http://localhost:8000/health/ready`.

For backend development: `cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload`.
For frontend development: run the API on port 8000, then `cd frontend && npm install && npm run dev`.

## Provider setup
Set model IDs only after checking the current provider catalogue:
- Gemini: `GEMINI_API_KEY`, `GEMINI_MODEL_FREE`, `GEMINI_MODEL_PREMIUM`
- Groq: `GROQ_API_KEY`, `GROQ_MODEL_BUDGET`, `GROQ_MODEL_LLAMA_70B`, `GROQ_MODEL_QWEN`
- DeepSeek: `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL_CHAT`, `DEEPSEEK_MODEL_REASONER`

`/api/v1/models` lists only aliases with both a model ID and provider key configured. `auto` uses the ordered `AI_FALLBACK_MODELS` setting and excludes Premium-only aliases for guest/free sessions. The initial chat adapter targets OpenAI-compatible text chat APIs; provider-specific image generation, grounding, audio and code-execution tools need separate adapters.

## API
- `GET /health/live` — liveness
- `GET /health/ready` — PostgreSQL and Redis readiness
- `GET /api/v1/models` — configured public model aliases
- `GET /api/v1/providers` — provider configuration status, never secrets
- `POST /api/v1/chat/completions` — OpenAI-style request with SSE streaming; stores history for signed-in users
- `GET /api/v1/conversations` — list the current user's saved chats
- `GET /api/v1/conversations/{id}/messages` — load saved chat messages
- `PATCH /api/v1/conversations/{id}` — rename a saved chat
- `DELETE /api/v1/conversations/{id}` — delete a saved chat
- `POST /api/v1/files/upload` — validate and privately store up to five files per request
- `GET /api/v1/files` — list the signed-in user's uploaded files
- `GET /api/v1/files/{id}/download` — owner-checked file download
- `DELETE /api/v1/files/{id}` — delete an uploaded file

## Security
Provider credentials remain server-side. Chat requires a guest or user session plus a CSRF token. Passwords use Argon2id, session tokens are opaque and stored in Redis by digest, sessions use HttpOnly cookies, and email verification tokens are single-use and time-limited. Redis rate limiting fails closed, CORS is explicit, API responses include security headers, and schema changes use Alembic. Configure SMTP before production registration is enabled. Saved conversation routes enforce ownership against the authenticated user. Guest sessions remain temporary. Uploads are private to the authenticated owner, size-limited by plan (10 MB Free, 50 MB Premium/Pro/Lifetime), and checked against extension and basic file signatures. Text, PDF, DOCX, XLSX, PPTX and ZIP file context is supported; old DOC files can be stored/downloaded but are not text-extracted. Images are stored, but OCR and image-model analysis are not yet enabled. **Malware scanning is not yet implemented**; do not treat signature checks as antivirus. Download only through the authenticated endpoint, never expose the storage volume as static web content.

## Checks
`cd backend && pip install -e ".[dev]" && ruff check app tests && pytest`
`cd frontend && npm install && npm run build`
