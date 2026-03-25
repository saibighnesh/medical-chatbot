# Medical Chatbot

A production-grade RAG (Retrieval-Augmented Generation) medical Q&A assistant with real-time streaming, multi-provider LLM support, and an admin dashboard for managing knowledge base and API keys.

> **Medical Disclaimer**: This chatbot provides general educational information only. It is **not** a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.

---

## Architecture

```
User → Flask (auth + rate-limit) → Input validation → FAISS similarity search
                                                            ↓
                                      Retrieved docs → Active LLM (Gemini / OpenAI / Claude)
                                                            ↓
                                            Streamed SSE response → User
```

### Stack

| Layer | Technology |
|-------|-----------|
| Web framework | Flask + Flask-Login + Flask-Limiter |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` |
| Vector store | FAISS (hot-reload after reindex) |
| LLM providers | Google Gemini · OpenAI GPT-4 · Anthropic Claude |
| LLM orchestration | LangChain |
| Streaming | Server-Sent Events (SSE) |
| Database | SQLite (WAL mode) |
| Encryption | AES-256 Fernet (API keys at rest) |
| Rate limiting | Flask-Limiter (Redis-backed in production) |
| Reverse proxy | Nginx (TLS, SSE buffering, security headers) |
| Container | Docker multi-stage + Docker Compose |
| CI/CD | GitHub Actions (6-job pipeline) |

---

## Features

- **Multi-provider LLM** — Switch between Gemini, OpenAI, and Claude from the dashboard without restarting the server
- **Streaming responses** — Tokens stream in real time via SSE
- **FAISS hot-reload** — Reindex triggers an in-memory reload; no restart needed
- **Emergency detection** — 20+ keyword patterns route urgent messages to 911 immediately
- **Prompt injection protection** — Regex patterns block common injection attempts
- **Confidence scoring** — Low-confidence retrievals surface a "consult a professional" warning
- **Source citations** — Every answer shows the source PDF and page number
- **Conversation memory** — Last 3 exchanges kept as context; history loads on page open
- **Admin dashboard** — Manage API keys, test them live, enable/disable documents, trigger reindex
- **Audit log** — All admin actions recorded with IP and timestamp
- **Rate limiting** — `/get`: 20/min · 200/day; `/login`: 10/min; `/signup`: 5/min
- **Structured logging** — JSON logs with per-request metrics

---

## Quick Start

### 1. Clone and install

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — at minimum set GOOGLE_API_KEY and SECRET_KEY
```

### 3. Add medical PDFs and build the index

```bash
# Place your PDFs in Data/
python store_index.py        # shows a live progress bar
```

### 4. Run

```bash
python app.py                # development (http://localhost:8080)
# or
docker-compose up --build    # production stack (Flask + Redis + Nginx)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | **Yes** | Flask session secret — generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `GOOGLE_API_KEY` | Yes* | Gemini API key — *at least one LLM key required |
| `OPENAI_API_KEY` | No | OpenAI API key (set via dashboard or env) |
| `ANTHROPIC_API_KEY` | No | Claude API key (set via dashboard or env) |
| `FLASK_ENV` | No | `development` or `production` (default: `production`) |
| `DATABASE_URL` | No | SQLite path (default: `users.db` in project root) |
| `REDIS_URL` | No | Redis URL for distributed rate limiting (e.g. `redis://localhost:6379/0`) |

---

## Project Structure

```
medical-chatbot/
├── app.py                     # Flask app — all routes, safety checks, streaming
├── store_index.py             # Build/rebuild FAISS index (tqdm progress bar)
├── auto_reindex_watcher.py    # Watchdog: auto-reindex when PDFs change in Data/
├── requirements.txt
├── .env.example
├── Dockerfile                 # Multi-stage production image
├── docker-compose.yml         # Dev/staging stack (Flask + Redis + Nginx)
├── docker-compose.production.yml  # Production stack (+ PostgreSQL)
├── pytest.ini                 # Test config (integration/slow markers)
├── pyproject.toml             # black + isort config
├── .flake8                    # flake8 config (120 char line length)
├── .github/
│   ├── workflows/
│   │   ├── ci-cd.yml          # 6-job CI/CD pipeline
│   │   └── integration.yml    # Nightly integration tests
│   └── dependabot.yml         # Automated dependency updates
├── nginx/
│   └── nginx.conf             # TLS, security headers, SSE buffering off
├── src/
│   ├── helper.py              # PDF loading, FAISS index creation, embeddings
│   ├── database.py            # SQLite — users, history, API keys, documents, audit
│   ├── llm_factory.py         # Multi-provider LLM factory (Gemini/OpenAI/Claude)
│   ├── encryption.py          # AES-256 Fernet for API key storage
│   ├── prompt.py              # System prompt template
│   └── logging_config.py      # JSON structured logging + metrics
├── templates/
│   ├── chat.html              # Chat UI (SSE streaming, history on load, citations)
│   ├── dashboard.html         # Admin dashboard (API keys + documents)
│   ├── login.html
│   ├── signup.html
│   ├── admin.html
│   └── metrics.html
├── tests/
│   ├── conftest.py
│   ├── test_api.py            # HTTP endpoint tests (28 tests, fully mocked)
│   ├── test_helper.py         # Unit tests for src/helper.py
│   ├── test_rag_pipeline.py   # Integration tests (marked @integration)
│   ├── test_quality.py        # Response quality assertions
│   └── test_performance.py    # Load and latency tests
└── Data/                      # Medical PDFs (not committed)
```

---

## Testing

```bash
# Fast tests only (CI mode — no model download)
pytest tests/test_api.py tests/test_helper.py -m "not integration and not slow"

# All tests including integration (downloads ~90MB model on first run)
pytest

# With coverage report
pytest --cov=src --cov=app --cov-report=html

# Single file
pytest tests/test_api.py -v
```

Test markers defined in `pytest.ini`:

| Marker | Meaning |
|--------|---------|
| `integration` | Requires live HuggingFace model download |
| `slow` | Heavy computation or long wait |
| `unit` | Fast, fully mocked |

---

## Admin Dashboard

Navigate to `http://localhost:8080/dashboard` (admin login required).

### API Keys tab
- Save Gemini, OpenAI, or Claude API keys — encrypted with AES-256 at rest
- **Test Key** — fires a real validation request before saving
- **Set as Active** — switches the live LLM instantly; no server restart needed
- Key preview shows only the last 4 characters

### Documents tab
- Drag-and-drop PDF upload (filename sanitized, path traversal prevented)
- Enable / Disable documents from the retrieval index
- Delete from DB and optionally from disk
- **Rebuild Index** — runs `store_index.py` and hot-reloads FAISS in memory

---

## CI/CD Pipeline

`.github/workflows/ci-cd.yml` runs on push/PR to `main`/`develop`:

```
PR    →  lint  →  security  →  test
push  →  lint  →  security  →  test  →  build  →  deploy-staging   (develop branch)
push  →  lint  →  security  →  test  →  build  →  deploy-production (main, approval gate)
```

| Job | Tools |
|-----|-------|
| `lint` | flake8 · black --check · isort --check-only |
| `security` | bandit · safety |
| `test` | pytest --cov · Codecov upload |
| `build` | docker buildx → ghcr.io · Trivy image scan |
| `deploy-staging` | SSH deploy to staging; health-check via `/health` |
| `deploy-production` | SSH deploy + 60s health-check loop + auto-rollback on failure |

Required GitHub secrets: `STAGING_HOST`, `STAGING_USER`, `STAGING_SSH_KEY`, `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`, `SECRET_KEY`, `CODECOV_TOKEN`.

---

## Security Highlights

| Control | Detail |
|---------|--------|
| Password policy | Min 8 chars · 1 uppercase · 1 number |
| Session cookies | `HTTPOnly` · `SameSite=Lax` · `Secure` in production |
| Rate limiting | Flask-Limiter; Redis-backed in production |
| File uploads | `secure_filename()` — path traversal prevented |
| SQL injection | 100% parameterized queries |
| API keys | AES-256 Fernet encrypted at rest |
| Security headers | Applied at both nginx and Flask levels |
| Debug mode | Off in production (`FLASK_ENV=production`) |

See [SECURITY.md](SECURITY.md) for the full security reference.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| FAISS index not loading | Run `python store_index.py` (needs PDFs in `Data/`) |
| `KeyError: GOOGLE_API_KEY` | `cp .env.example .env` then fill in your keys |
| Port 8080 in use | `FLASK_RUN_PORT=5001 python app.py` |
| 429 rate limit errors | Wait 1 minute; or increase limits in `app.py` for dev |
| LLM not switching after dashboard change | Send one message — cache reloads on next request |
| Docker build slow | First build downloads the HuggingFace model; subsequent builds use layer cache |

---

## License

Educational use. Medical content must be verified by qualified healthcare professionals before clinical application.
