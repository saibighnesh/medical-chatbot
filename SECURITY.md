# Security Guide

Security controls implemented in the Medical Chatbot and guidance for secure deployment.

---

## Authentication & Session Management

| Control | Detail |
|---------|--------|
| Password hashing | bcrypt via Werkzeug — automatic per-password salt, constant-time verification |
| Password policy | Minimum 8 characters · at least 1 uppercase letter · at least 1 number |
| Username policy | 3–30 characters · only `[a-zA-Z0-9_-]` — blocks SQL-hostile or XSS-prone characters |
| Session cookies | `HTTPOnly=True` (JS cannot read) · `SameSite=Lax` (CSRF mitigation) · `Secure=True` in production only |
| Session fixation | Session regenerated on login |
| Login rate limit | 10 POST attempts per minute per IP (Flask-Limiter) |
| Signup rate limit | 5 POST attempts per minute per IP |
| Failed login logging | IP address and username logged on every failure |

---

## Input Validation & Injection Prevention

### Chat endpoint (`/get`)

- **2000-character limit** on all messages
- **Prompt injection patterns** blocked by regex:
  - `ignore previous/above/all instructions`
  - `system: you are`
  - `<script>` tags
  - `DROP TABLE`, `DELETE FROM`
- **Emergency keywords** (20+ patterns) short-circuit the LLM call and return a 911 message immediately — no API cost, no delay
- **POST only** — the endpoint no longer accepts GET requests

### File uploads (`/admin/upload`)

- `werkzeug.utils.secure_filename()` applied to every uploaded filename
  - Strips path separators (`../`, `../../`) — prevents path traversal
  - Returns empty string for dangerous filenames → rejected with 400
- Extension check: `.pdf` only (case-insensitive)
- File size validated by PDF reader

### User inputs

- `request.form.get()` used throughout — never `request.form["key"]` which raises unhandled KeyError
- Raw exception messages (`str(e)`) never returned to the client — logged server-side, client receives a generic message

---

## API Key Security

API keys (Gemini, OpenAI, Claude) entered in the dashboard are:

1. **Encrypted** with AES-256 Fernet before writing to SQLite
2. **Key derivation**: PBKDF2-HMAC-SHA256 (100,000 iterations) applied to Flask `SECRET_KEY`
3. **Preview only**: The dashboard shows `****<last4>` — the full key is never sent to the browser
4. **Decrypted at runtime** only, in memory, for each LLM call
5. **Validated before saving**: The "Test Key" button fires a real API call before any key is persisted

---

## Rate Limiting

Implemented with Flask-Limiter. Backed by Redis when `REDIS_URL` is set (production), in-memory otherwise (development).

| Endpoint | Limit |
|----------|-------|
| `POST /get` (chat) | 20 per minute · 200 per day per IP |
| `POST /login` | 10 per minute per IP |
| `POST /signup` | 5 per minute per IP |

Nginx adds a second layer: `limit_req zone=chat_limit burst=5 nodelay` on `/get`.

---

## Database Security

- **100% parameterized queries** — no string-formatted SQL anywhere
- **WAL mode** enabled on every connection — eliminates write-lock contention under concurrent load
- **Foreign key enforcement** — `PRAGMA foreign_keys=ON` on every connection
- `save_chat_history()` wrapped in `try/finally` — a DB write failure is logged but never crashes the SSE stream
- Database file (`users.db`) listed in `.gitignore` — never committed

---

## Transport & Headers

### Nginx (production)

```
X-Frame-Options: SAMEORIGIN
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- HTTP → HTTPS redirect (port 80 → 443)
- TLS 1.2 / 1.3 only, strong ciphers
- SSE endpoint (`/get`): `proxy_buffering off` — tokens stream to the client immediately

### Flask (all environments)

`after_request` hook applies the same security headers to every Flask response, so they're present even when the app is accessed directly without nginx (development, CI):

```
X-Frame-Options, X-Content-Type-Options, X-XSS-Protection,
Referrer-Policy, Content-Security-Policy
```

---

## Subprocess & Information Disclosure

The `/admin/reindex` route runs `store_index.py` as a subprocess. Previously the full `stdout`/`stderr` was returned in the API response (information leakage). Now:

- `stdout` is logged (truncated to 500 chars) at `INFO` level
- `stderr` is logged (truncated to 500 chars) at `ERROR` level
- The client receives only `"Index rebuild failed. Check server logs for details."` on failure

---

## Admin Access Controls

All admin routes check `current_user.is_admin` explicitly — Flask-Login's `@login_required` alone is not sufficient. Unauthorized requests receive `403` (not `404`) so the route existence is not hidden.

Audit log entries are written for:

| Action | Details logged |
|--------|---------------|
| Save API key | provider name |
| Delete API key | provider name |
| Activate provider | provider name |
| Delete document | filename |
| Any admin action | user ID, IP address, timestamp |

---

## Docker & Container Security

- **Multi-stage build** — only the compiled venv is copied to the runtime image, not gcc or build tools
- **Non-root user** — container runs as `appuser` (UID 1000)
- **`.dockerignore`** excludes `venv/`, `.env`, `faiss_index/`, `logs/`, `*.db` — secrets and large artifacts never enter the image
- **Health check** — `curl -f http://localhost:8080/health` (lightweight JSON endpoint, no auth required)
- `debug=False` in production — Werkzeug interactive debugger is disabled (enabled only when `FLASK_ENV=development`)

---

## Production Hardening Checklist

### Before first deployment

- [ ] Generate `SECRET_KEY` with `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Set `FLASK_ENV=production`
- [ ] Set `REDIS_URL` for distributed rate limiting
- [ ] Configure TLS certificate (Let's Encrypt recommended)
- [ ] Set firewall to block port 8080 from public access (proxy via Nginx only)
- [ ] Rotate default admin password immediately after first login

### Ongoing

- [ ] Monitor failed login logs: `grep "Failed login" logs/app.log`
- [ ] Review audit log weekly: `SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 100`
- [ ] Keep dependencies updated (Dependabot PRs auto-created weekly)
- [ ] Renew TLS certificate before expiry (`certbot renew`)
- [ ] Back up `users.db` and `faiss_index/` daily

---

## Reporting Vulnerabilities

If you discover a security issue, please report it responsibly:

- **Do not** open a public GitHub issue
- Email the maintainer directly with a description and reproduction steps
- Allow reasonable time to patch before public disclosure

---

## Known Limitations

| Limitation | Mitigation |
|-----------|-----------|
| SQLite not suitable for large multi-server deployments | Use `docker-compose.production.yml` (PostgreSQL) |
| In-memory rate limiting doesn't persist across gunicorn workers | Set `REDIS_URL` in production |
| No two-factor authentication | Compensated by rate limiting + audit log |
| No email verification on signup | Admin can delete fraudulent accounts via DB |
| CSP allows `'unsafe-inline'` (templates use inline scripts) | Planned: move to external JS files in future |
