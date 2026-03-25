# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a **production-grade RAG (Retrieval-Augmented Generation) medical Q&A chatbot** using:
- **Flask** web server with Server-Sent Events (SSE) for real-time token streaming
- **FAISS** vector store with HuggingFace `sentence-transformers/all-MiniLM-L6-v2` embeddings
- **Multi-provider LLM** — Google Gemini 2.5 Flash / OpenAI GPT-4o / Anthropic Claude, switchable at runtime via the admin dashboard
- **SQLite** (WAL mode) for user accounts, chat history, API keys, documents, and audit log
- **Flask-Limiter** for rate limiting (Redis-backed in production)
- **AES-256 Fernet** encryption for API keys stored in the database

## Setup & Running

```bash
# Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment (requires at minimum GOOGLE_API_KEY and SECRET_KEY)
cp .env.example .env

# Build FAISS index from PDFs in Data/ (required before first run)
python store_index.py

# Run locally (http://localhost:8080)
python app.py

# Production stack (Flask + Redis + Nginx)
docker-compose up --build
```

## Common Commands

```bash
# Run fast tests only (no model download)
pytest tests/test_api.py tests/test_helper.py -m "not integration and not slow"

# Run all tests (integration tests download ~90MB HuggingFace model on first run)
pytest

# Run with coverage
pytest --cov=src --cov=app --cov-report=html

# Single file
pytest tests/test_api.py -v

# Rebuild FAISS index after adding PDFs to Data/
python store_index.py

# Auto-watch Data/ and reindex on changes
python auto_reindex_watcher.py

# Docker production stack with PostgreSQL
docker-compose -f docker-compose.production.yml up -d
```

## Architecture

```
User → Flask (auth + rate-limit) → Input validation → FAISS similarity search
                                                            ↓
                                      Retrieved docs → Active LLM (Gemini / OpenAI / Claude)
                                                            ↓
                                            Streamed SSE response → User
```

### Request flow for `/get` (chat endpoint)

1. `@limiter.limit("20 per minute; 200 per day")` — rate limit enforced before handler runs
2. `detect_emergency()` — checks 20+ emergency keywords; returns 911 message immediately if matched (no LLM call)
3. `validate_input()` — regex-based prompt injection prevention, 2000-char limit
4. FAISS retrieval — top-k similar chunks from active documents in `Data/`
5. `calculate_response_confidence()` — scores retrieved docs; surfaces a warning if confidence is low
6. Active LLM generates response with medical disclaimer, streamed token-by-token via SSE
7. `save_chat_history()` called in try/finally — DB failure is logged but never crashes the stream

### LLM provider switching

`get_active_llm()` in `app.py` caches the current provider. On each chat request it checks `get_active_provider()` from the database. If the provider has changed (set via the dashboard), it rebuilds the LLM instance transparently — no server restart required.

### FAISS hot-reload

`/admin/reindex` runs `store_index.py` as a subprocess, then calls `_load_faiss_index()` to reload the in-memory retriever. The subprocess stdout/stderr is logged server-side only — never returned to the client.

## Key Source Files

| File | Purpose |
|------|---------|
| `app.py` | All Flask routes, safety checks, LLM caching, SSE streaming |
| `src/helper.py` | PDF loading, FAISS index creation, embedding utilities |
| `src/database.py` | SQLite — users, history, API keys, documents, audit log; `_connect()` sets WAL + foreign keys |
| `src/llm_factory.py` | Multi-provider LLM factory (Gemini / OpenAI / Claude) + API key validation |
| `src/encryption.py` | AES-256 Fernet encryption for API keys; PBKDF2-HMAC-SHA256 key derivation from SECRET_KEY |
| `src/prompt.py` | LLM system prompt template |
| `src/logging_config.py` | JSON structured logging and per-request metrics |
| `store_index.py` | Build/rebuild FAISS index with tqdm progress bar; batches embeddings in groups of 50 |
| `auto_reindex_watcher.py` | Watchdog that auto-rebuilds index when PDFs change in `Data/` |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | **Yes** | Flask session secret — `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_API_KEY` | Yes* | Gemini API key (*at least one LLM key required) |
| `OPENAI_API_KEY` | No | OpenAI key; can also be set via dashboard |
| `ANTHROPIC_API_KEY` | No | Claude key; can also be set via dashboard |
| `FLASK_ENV` | No | `development` or `production` (default: `production`) |
| `DATABASE_URL` | No | SQLite path (default: `users.db` in project root) |
| `REDIS_URL` | No | Redis URL for distributed rate limiting — required in production with multiple gunicorn workers |

## Database Schema

Tables in `users.db` (initialized by `src/database.py:init_db()`):

- `users` — username, email, bcrypt password hash, is_admin flag
- `chat_history` — user_id (FK), question, answer, created_at
- `api_keys` — provider, encrypted_key, is_active, updated_at
- `documents` — filename, original_name, file_path, file_size, page_count, is_active, status, created_at
- `audit_log` — user_id (FK), action, details, ip_address, created_at

All queries use parameterized statements. Every connection applies `PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON` via `_connect()`.

## Security Controls

- **Rate limiting**: Flask-Limiter; Redis-backed in production (`REDIS_URL`), in-memory otherwise
- **Session cookies**: `HTTPOnly=True`, `SameSite=Lax`, `Secure=True` in production
- **Security headers**: Applied in `after_request` hook (X-Frame-Options, X-Content-Type-Options, CSP, etc.) and by nginx
- **File uploads**: `secure_filename()` applied to every uploaded filename; `.pdf` extension enforced
- **API keys**: AES-256 Fernet encrypted before writing to SQLite; PBKDF2-HMAC-SHA256 key derivation
- **Subprocess output**: stdout/stderr logged server-side only — generic message returned to client
- **Password policy**: Min 8 chars, 1 uppercase, 1 number (enforced in signup route)
- **Debug mode**: Off in production — `debug=True` only when `FLASK_ENV=development`

## Admin Dashboard

Navigate to `http://localhost:8080/dashboard` (requires `is_admin=1` in the database).

- **API Keys tab**: Save/test/activate Gemini, OpenAI, or Claude keys
- **Documents tab**: Upload PDFs, toggle active status, rebuild FAISS index, delete documents

To create the first admin user:
```bash
sqlite3 users.db "UPDATE users SET is_admin = 1 WHERE username = 'your-username';"
```

## Testing

Test markers (defined in `pytest.ini`):

| Marker | Meaning |
|--------|---------|
| `integration` | Requires live HuggingFace model download (~90MB on first run) |
| `slow` | Heavy computation or long wait |
| `unit` | Fast, fully mocked |

5 tests in `tests/test_helper.py` are marked `@pytest.mark.integration` — they are excluded from CI's fast test run and run nightly via `.github/workflows/integration.yml`.

## Generated Artifacts (not committed)

- `faiss_index/` — Built by `store_index.py` from PDFs in `Data/`
- `logs/` — JSON application logs
- `users.db` — SQLite database
- `Data/` — Medical PDFs (not committed; must be provided)
