# Enterprise AI Knowledge & Document Intelligence Platform

A production-oriented enterprise AI platform built on Python, FastAPI, LangChain, FAISS, and Ollama.

---

## What this is

An internal knowledge platform for large organisations that combines:

- **Secure multi-role authentication** (email/password + email OTP)
- **Role-Based Access Control** (SUPER_ADMIN / ADMIN / EMPLOYEE / STUDENT)
- **Document-level permissions** — the RAG pipeline only retrieves documents the authenticated user is authorised to see
- **Advanced RAG** — hybrid semantic + keyword retrieval, cross-encoder reranking, anti-hallucination prompts, source citations
- **AI Guide Agent** — intent-aware agent with a modular, permission-enforced tool registry
- **Audit logging** — every sensitive operation is recorded
- **Streamlit frontend** — enterprise dark-theme UI with role-aware navigation

---

## Stage completion status

| Stage | Description | Status |
|-------|-------------|--------|
| **1** | FastAPI foundation + project structure + RAG pipeline | ✅ Complete |
| **2** | PostgreSQL + SQLAlchemy + Alembic migrations | ✅ Scaffolded |
| **3** | User registration + password auth | ✅ Implemented |
| **4** | Email OTP | ✅ Implemented |
| **5** | JWT sessions + refresh tokens | ✅ Implemented |
| **6** | RBAC + permission decorators | ✅ Implemented |
| **7** | Document-level permissions | ✅ Implemented |
| **8** | Document management + multi-format upload | ✅ Implemented |
| **9** | Background ingestion (Redis + Celery) | ⚠️ FastAPI background worker |
| **10** | Advanced RAG / hybrid retrieval / reranking | ✅ Complete (pipeline ready) |
| **11** | Conversation history | ✅ Implemented |
| **12** | Admin dashboard | ✅ Initial implementation |
| **13** | Audit logs | ✅ Initial implementation |
| **14** | RAG evaluation framework | ✅ Retrieval evaluator |
| **15** | Docker + production config | ✅ Local Compose scaffold |
| **16** | AI Guide Agent | ✅ Initial slice complete |

---

## Project structure

```
enterprise-ai-platform/
│
├── app/
│   ├── main.py                   ← FastAPI app, middleware, routers
│   ├── api/v1/
│   │   ├── auth.py               ← Authentication endpoints
│   │   ├── users.py              ← User management
│   │   ├── documents.py          ← Document upload / management
│   │   ├── chat.py               ← RAG chat + conversations
│   │   ├── conversations.py      ← Conversation history
│   │   └── admin.py              ← Admin dashboard + audit logs
│   ├── auth/                     ← password.py, otp.py, jwt.py, permissions.py
│   ├── core/
│   │   ├── config.py             ← Pydantic BaseSettings (all env vars)
│   │   ├── logging.py            ← JSON/dev logging, RAGTrace, AgentTrace
│   │   └── security.py           ← bcrypt, JWT, OTP utils, file validation
│   ├── database/                 ← SQLAlchemy models + Alembic (Stage 2)
│   ├── rag/
│   │   ├── embeddings.py         ← HuggingFace all-MiniLM-L6-v2 (cached)
│   │   ├── loader.py             ← PDF / DOCX / TXT / MD / HTML
│   │   ├── splitter.py           ← Recursive + Markdown-aware chunking
│   │   ├── vector_store.py       ← Persistent FAISS, per-doc delete, auth filter
│   │   ├── retriever.py          ← Hybrid: semantic + keyword TF-IDF + RRF fusion
│   │   ├── reranker.py           ← Cross-encoder ms-marco-MiniLM
│   │   ├── prompts.py            ← Anti-hallucination prompt, citations
│   │   └── pipeline.py           ← EnterpriseRAGPipeline + RAGResponse
│   ├── agent/                    ← AI Guide Agent (Stage 16)
│   ├── workers/                  ← Background ingestion (Stage 9)
│   └── schemas/
│       ├── auth.py
│       ├── users.py
│       ├── documents.py
│       └── chat.py
│
├── frontend/
│   ├── streamlit_app.py          ← Streamlit setup, theme, and app entry point
│   ├── api.py                    ← Centralized FastAPI client and response helpers
│   ├── components.py             ← Shared AppShell, sidebar, topbar, and UI helpers
│   ├── constants.py              ← Navigation and session defaults
│   └── pages.py                  ← Login, dashboard, documents, chat, guide, history, and admin
│
├── tests/                        ← pytest suite
├── evaluation/                   ← RAG evaluation scripts (Stage 14)
├── migrations/                   ← Alembic migrations (Stage 2)
├── data/
│   ├── uploads/                  ← Uploaded documents
│   └── vector_store/             ← Persistent FAISS index
│
├── .env.example                  ← Copy to .env and fill in values
├── requirements.txt
└── README.md
```

---

## Quick start (Stage 1 — no database required)

### 1. Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) running locally with `llama3.2:1b` pulled

```bash
ollama pull llama3.2:1b
```

### 2. Create virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
copy .env.example .env     # Windows
# cp .env.example .env     # macOS / Linux
```

Edit `.env` — at minimum set `OLLAMA_HOST` (default `http://localhost:11434`).

### 5. Start the FastAPI backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/api/v1/docs
- Health:   http://localhost:8000/health

### 6. Start the Streamlit frontend

```bash
streamlit run frontend/streamlit_app.py
```

Frontend: http://localhost:8501

### 7. Test the RAG endpoint

```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
     -H "Content-Type: application/json" \
     -d '{"question": "What documents are available?"}'
```

---

## API overview

All endpoints are versioned under `/api/v1/`.

| Prefix | Description |
|--------|-------------|
| `/api/v1/auth/*` | Registration, login, OTP, logout, refresh, /me |
| `/api/v1/users/*` | User management (ADMIN+) |
| `/api/v1/documents/*` | Upload, list, delete, re-index, permissions |
| `/api/v1/chat/*` | RAG ask, AI agent, conversation CRUD |
| `/api/v1/conversations/*` | Conversation management |
| `/api/v1/admin/*` | Dashboard stats, system health, audit logs |

Interactive docs: **http://localhost:8000/api/v1/docs**

---

## Security design

- Passwords hashed with **bcrypt** (work factor 12) — never stored in plaintext
- OTPs hashed with bcrypt before storage — never logged
- **JWT** access tokens (30 min) + refresh tokens (7 days)
- **RBAC** enforced on the backend — frontend checks are supplementary only
- Document retrieval is filtered by `allowed_document_ids` **before** the LLM sees any content
- All secrets via environment variables — no hardcoded credentials
- Request IDs on every response for tracing

---

## Environment variables

See `.env.example` for the full list with descriptions.

Key variables:

| Variable | Description |
|----------|-------------|
| `JWT_SECRET_KEY` | 64-byte hex secret for JWT signing |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `OLLAMA_HOST` | Ollama server URL |
| `ALLOWED_EMAIL_DOMAINS` | Comma-separated allowed domains (empty = all) |
| `EMAIL_HOST` / `EMAIL_PASSWORD` | SMTP credentials for OTP emails |

## Production deployment

The current repository uses SQLAlchemy (SQLite by default, PostgreSQL supported), local FAISS files, and local PDF files when `S3_BUCKET` is empty. It does **not** currently use MongoDB. Do not deploy the SQLite database or `data/uploads` as Vercel function storage.

Recommended production topology:

- Deploy `web/` to Vercel with `API_BACKEND_URL` set to the HTTPS origin of the separately hosted FastAPI service.
- Run FastAPI and the existing Celery worker on a persistent container platform. Use managed PostgreSQL through `DATABASE_URL`, managed Redis through `REDIS_URL`, and set `CELERY_ENABLED=true` so indexing is queued rather than tied to a request process.
- Set `S3_BUCKET` (and region/endpoint/credentials or the host IAM role) for persistent uploaded PDFs.
- Mount the same persistent shared filesystem, such as AWS EFS, at the same path for every API instance and Celery worker. Set `VECTOR_STORE_PATH` to its `vector_store` directory. The FAISS index format and retrieval algorithm remain unchanged; a Redis lock serializes production index mutations and a generation marker makes other instances reload updates.
- Keep `JWT_SECRET_KEY` identical and stable on every API instance. Set `CORS_ORIGINS` to the deployed frontend origin if the API is accessed directly; the browser normally calls the same-origin Next.js `/api` rewrite.

The backend refuses `APP_ENV=production` startup when it detects SQLite, local-only file storage, disabled Celery, a loopback Redis/LLM endpoint, or a relative FAISS path. Apply database migrations before starting production traffic:

```bash
alembic upgrade head
```

Deploy the Next.js project from the `enterprise-ai-platform/web` root with build command `npm run build`. Deploy FastAPI separately from `enterprise-ai-platform` using the existing `app.main:app` entrypoint and the host's persistent container command, for example `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Run the existing Celery worker as a separate long-lived service using `celery -A app.workers.celery_app.celery_app worker --loglevel=info`.

The `pyproject.toml` Vercel entrypoint remains configured for `app.main:app` if deploying that backend as a Vercel Function is explicitly required, but Vercel functions do not provide the shared EFS mount or long-lived Celery worker required by this storage topology. A Vercel-only backend deployment is therefore not the recommended production setup for this FAISS-based application.

---

## Running tests

```bash
pytest tests/ -v
```

---

## Next step — Stage 2

Stage 2 will add:
- PostgreSQL database with SQLAlchemy async models
- Alembic migration scripts
- All database tables: users, roles, otp_codes, sessions, documents, audit_logs, conversations, messages

Run `python -m pytest tests/` after each stage to verify nothing regresses.

## AI Guide Agent (Stage 16 initial slice)

`POST /api/v1/chat/agent` is authenticated and routes requests through an
explicit tool registry. The initial tools are authorized document search,
policy search, and confirmation-gated support-ticket creation. RAG calls use
the authenticated user's document allow-list before retrieval. Unsupported or
ambiguous requests receive a clarification response rather than arbitrary
backend execution.

Action responses include `pending_confirmation`; send that object back as
`pending_action` with `confirm_action: true` to execute the approved action.
