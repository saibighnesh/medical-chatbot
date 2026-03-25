# API Reference

Medical Chatbot REST API — complete endpoint reference.

## Base URL

```
http://localhost:8080      # development
https://your-domain.com   # production (via nginx)
```

## Authentication

Session-cookie based (Flask-Login). Log in via `POST /login` to receive a session cookie, then include it in subsequent requests.

All protected endpoints return a `302` redirect to `/login` if the session is missing or expired.

---

## Public Endpoints

### `GET /health`

Lightweight health check — no authentication required. Used by CI/CD deploy scripts and load balancers.

**Response**
```json
{"status": "ok", "index_loaded": true}
```

`index_loaded` is `false` if `store_index.py` has not been run yet.

---

### `GET /login`

Returns the login HTML page.

---

### `POST /login`

Authenticate and create a session.

Rate limit: **10 per minute per IP**

**Request** (form data)
```
username=string  (required)
password=string  (required)
```

**Response**
- Success → `302` redirect to `/`
- Failure → `200` with error message on the login page

---

### `GET /signup`

Returns the signup HTML page.

---

### `POST /signup`

Create a new user account.

Rate limit: **5 per minute per IP**

**Request** (form data)
```
username=string          (3–30 chars, [a-zA-Z0-9_-] only)
email=string             (valid email format)
password=string          (min 8 chars, 1 uppercase, 1 number)
confirm_password=string
```

**Response**
- Success → `200` login page with success message
- Validation failure → `200` signup page with error message

---

## Protected Endpoints (login required)

### `GET /`

Returns the chat interface HTML. Passes `username` and `active_provider` (e.g. `"Gemini"`) to the template.

---

### `POST /get`

Send a message to the chatbot. Returns a Server-Sent Events stream.

Rate limit: **20 per minute · 200 per day per IP**

**Request** (form data)
```
msg=string   (required, max 2000 characters)
```

**Response** — `Content-Type: text/event-stream`

Each SSE event is a JSON object on a `data:` line:

```
data: {"token": "Diabetes "}

data: {"token": "is a chronic..."}

data: {"sources": [{"content": "...", "metadata": {"source": "book.pdf", "page": 12}}]}

data: {"done": true, "confidence": 0.8, "sources": [...]}
```

**Emergency detection** — if the message contains an emergency keyword, the stream returns:
```
data: {"token": "🚨 EMERGENCY DETECTED...call 911..."}

data: {"done": true, "emergency": true}
```

**Error events**
```
data: {"token": "Please enter a question.", "error": true}
data: {"done": true}
```

Possible error conditions:
- Empty message
- Message longer than 2000 characters
- Prompt injection pattern detected
- FAISS index not loaded
- LLM API failure

---

### `GET /history`

Retrieve the authenticated user's chat history (most recent 50 exchanges).

**Response**
```json
{
  "history": [
    {
      "question": "What is diabetes?",
      "answer": "Diabetes is a chronic condition...",
      "created_at": "2026-03-25T10:30:00"
    }
  ]
}
```

---

### `POST /clear-history`

Clear all chat history for the current user (session + database).

**Response**
```json
{"success": true, "message": "Conversation history cleared"}
```

Error (500):
```json
{"success": false, "message": "Failed to clear database history"}
```

---

### `GET /metrics`

Metrics dashboard HTML page (admin only in practice, any logged-in user can access).

---

### `GET /api/metrics`

JSON metrics snapshot.

**Response**
```json
{
  "uptime_seconds": 3600,
  "total_requests": 142,
  "total_errors": 3,
  "error_rate_percent": 2.1,
  "avg_response_time_ms": 1240,
  "endpoints": {
    "chat": {"count": 98, "avg_response_time": 1.8, "error_rate": 1.0}
  }
}
```

---

## Admin Endpoints (admin login required)

All admin endpoints return `403` for non-admin users.

### `GET /admin`

Admin panel HTML page.

---

### `POST /admin/upload`

Upload a PDF to the knowledge base.

**Request** — multipart/form-data
```
file=<PDF file>
```

**Validation**
- Extension must be `.pdf` (case-insensitive)
- Filename sanitized with `secure_filename()` (path traversal prevented)
- Page count extracted and stored

**Response**
```json
{
  "success": true,
  "filename": "clinical_guide.pdf",
  "message": "File uploaded successfully. Re-index to make it searchable."
}
```

Error responses: `400` (no file / invalid extension / invalid filename), `403` (not admin), `500` (internal error — details logged server-side)

---

### `POST /admin/reindex`

Rebuild the FAISS index from all PDFs in `Data/`, then hot-reload it in memory.

**Response**
```json
{"success": true, "message": "Index rebuilt and reloaded successfully"}
```

Error: `500` — `{"error": "Index rebuild failed. Check server logs for details."}`

Timeout: `500` — `{"error": "Indexing timed out (>5 minutes)"}`

---

### `GET /admin/stats`

Quick stats for the legacy admin panel.

**Response**
```json
{"pdf_count": 5, "index_exists": true}
```

---

## Dashboard API Endpoints (admin only)

### `GET /dashboard`

Dashboard HTML page.

---

### `GET /dashboard/api/keys`

List all saved API keys (key preview only — last 4 chars).

**Response**
```json
{
  "keys": [
    {
      "provider": "gemini",
      "is_active": true,
      "has_key": true,
      "key_preview": "****xYz1",
      "updated_at": "2026-03-25 10:00:00"
    }
  ],
  "active_provider": "gemini"
}
```

---

### `POST /dashboard/api/keys`

Save or update an API key.

**Request** (JSON)
```json
{"provider": "gemini", "api_key": "AIzaSy..."}
```

Providers: `gemini`, `openai`, `claude`

**Response**
```json
{"success": true, "message": "Gemini key saved"}
```

Errors: `400` (invalid provider / empty key), `500` (save failed)

---

### `DELETE /dashboard/api/keys/<provider>`

Delete a saved API key.

**Response**
```json
{"success": true}
```

---

### `POST /dashboard/api/keys/<provider>/activate`

Set a provider as the active LLM. Takes effect on the next chat request.

**Response**
```json
{"success": true, "message": "Gemini is now active"}
```

Error: `400` if no key is saved for the provider.

---

### `POST /dashboard/api/keys/validate`

Test an API key by making a real (small) request to the provider.

**Request** (JSON)
```json
{"provider": "openai", "api_key": "sk-..."}
```

If `api_key` is omitted, validates the currently saved key.

**Response**
```json
{"valid": true, "message": "Openai API key is valid", "response": "OK"}
```

```json
{"valid": false, "message": "API key validation failed: Incorrect API key provided"}
```

---

### `GET /dashboard/api/documents`

List all tracked documents plus any untracked PDFs found on disk.

**Response**
```json
{
  "documents": [
    {
      "id": 1,
      "filename": "clinical_guide.pdf",
      "original_name": "clinical_guide.pdf",
      "file_path": "Data/clinical_guide.pdf",
      "file_size": 2048576,
      "page_count": 142,
      "is_active": true,
      "status": "indexed",
      "on_disk": true,
      "created_at": "2026-03-25 09:00:00"
    }
  ]
}
```

`status` values: `pending_index`, `indexed`, `untracked` (on disk, not in DB), `missing` (in DB, not on disk)

---

### `POST /dashboard/api/documents/<id>/toggle`

Toggle a document's `is_active` flag.

**Response**
```json
{"success": true, "is_active": false}
```

---

### `DELETE /dashboard/api/documents/<id>`

Delete a document record from the database.

Query param: `?remove_file=true` also deletes the file from disk.

**Response**
```json
{"success": true}
```

---

### `GET /dashboard/api/stats`

Dashboard summary stats.

**Response**
```json
{
  "pdf_count": 5,
  "index_exists": true,
  "active_provider": "gemini"
}
```

---

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `302` | Redirect (after login/logout, or unauthenticated access) |
| `400` | Bad request — invalid input |
| `403` | Forbidden — logged in but not admin |
| `404` | Not found |
| `405` | Method not allowed |
| `429` | Rate limit exceeded |
| `500` | Internal server error — details in server logs, not in response body |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| `POST /get` | 20 per minute · 200 per day per IP |
| `POST /login` | 10 per minute per IP |
| `POST /signup` | 5 per minute per IP |

Rate limits are enforced by Flask-Limiter using in-memory storage (dev) or Redis (`REDIS_URL` env var, production).

429 responses include a `Retry-After` header.
