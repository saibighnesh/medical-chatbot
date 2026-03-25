# Deployment Guide

Production deployment guide for the Medical Chatbot.

---

## Pre-Deployment Checklist

- [ ] All tests pass: `pytest tests/test_api.py tests/test_helper.py -m "not integration"`
- [ ] FAISS index built from production PDFs: `python store_index.py`
- [ ] `SECRET_KEY` set to a 32+ character random string
- [ ] `FLASK_ENV=production` set
- [ ] At least one LLM API key configured
- [ ] HTTPS certificate ready
- [ ] Firewall blocks direct access to port 8080 (proxy via nginx only)
- [ ] Redis available for distributed rate limiting
- [ ] Backup strategy in place

---

## Option 1 — Docker Compose (recommended)

The fastest path to a running production stack.

```bash
# Clone project
git clone <your-repo> /opt/medical-chatbot
cd /opt/medical-chatbot

# Configure environment
cp .env.example .env
# Edit .env: set SECRET_KEY, GOOGLE_API_KEY, FLASK_ENV=production, REDIS_URL

# Place PDFs in Data/ then build the index
python store_index.py

# Start the full stack (Flask + Redis + Nginx)
docker-compose up -d --build

# Verify
curl -f http://localhost/health
```

The compose file starts:
- **medbot** — Flask app via gunicorn (4 workers)
- **redis** — Rate-limit storage and session backend
- **nginx** — Reverse proxy, TLS termination, SSE buffering

For PostgreSQL + production hardening use:
```bash
docker-compose -f docker-compose.production.yml up -d
```

### Health check

All containers include Docker health checks:
```bash
docker ps          # shows health status
docker inspect medbot | jq '.[0].State.Health'
```

---

## Option 2 — Gunicorn + Nginx (bare metal / VM)

### System requirements

| Spec | Minimum | Recommended |
|------|---------|-------------|
| CPU | 2 cores | 4 cores |
| RAM | 4 GB | 8 GB |
| Disk | 10 GB | 50 GB SSD |
| OS | Ubuntu 20.04+ | Ubuntu 22.04 LTS |

### Install

```bash
sudo apt update && sudo apt install -y python3.10 python3.10-venv nginx redis-server

# Application directory
sudo mkdir -p /opt/medical-chatbot
cd /opt/medical-chatbot
# copy project files here

python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment

Create `/opt/medical-chatbot/.env`:
```bash
SECRET_KEY=<32+ char random string>
GOOGLE_API_KEY=<your key>
FLASK_ENV=production
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=sqlite:////opt/medical-chatbot/users.db
```

```bash
chmod 600 .env    # readable by app user only
```

Generate a strong secret key:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Build index

```bash
source venv/bin/activate
python store_index.py
```

### Systemd service

Create `/etc/systemd/system/medical-chatbot.service`:
```ini
[Unit]
Description=Medical Chatbot
After=network.target redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/medical-chatbot
EnvironmentFile=/opt/medical-chatbot/.env
ExecStart=/opt/medical-chatbot/venv/bin/gunicorn \
    --bind 127.0.0.1:8080 \
    --workers 4 \
    --timeout 120 \
    --access-logfile /var/log/medical-chatbot/access.log \
    --error-logfile /var/log/medical-chatbot/error.log \
    app:app
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo mkdir -p /var/log/medical-chatbot
sudo chown www-data:www-data /var/log/medical-chatbot
sudo systemctl daemon-reload
sudo systemctl enable --now medical-chatbot
```

### Nginx

Copy `nginx/nginx.conf` (included in repo) to `/etc/nginx/nginx.conf` and update `server_name`. The config includes:
- HTTP → HTTPS redirect
- TLS 1.2/1.3
- HSTS
- Security headers (`X-Frame-Options`, `X-Content-Type-Options`, CSP, etc.)
- `proxy_buffering off` on `/get` — required for SSE token streaming
- `/health` with `access_log off` — suppresses health-check noise

```bash
sudo nginx -t && sudo systemctl restart nginx
```

### TLS (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

Auto-renewal is configured by certbot automatically.

---

## Creating the First Admin User

After the app starts, connect to the SQLite database to promote a user:

```bash
sqlite3 /opt/medical-chatbot/users.db \
  "UPDATE users SET is_admin = 1 WHERE username = 'your-username';"
```

Or sign up normally then update the row, or create via Python:

```bash
cd /opt/medical-chatbot && source venv/bin/activate
python - <<'EOF'
from src.database import User
u = User.create('admin', 'admin@example.com', 'StrongPass1')
print(f"Created user id={u.id}")
EOF
sqlite3 users.db "UPDATE users SET is_admin = 1 WHERE username = 'admin';"
```

---

## Backups

### What to back up

| Item | Location |
|------|----------|
| Database | `users.db` |
| FAISS index | `faiss_index/` |
| PDFs | `Data/` |
| Environment | `.env` (store encrypted) |

### Daily backup script

```bash
#!/bin/bash
DEST="/backup/medical-chatbot/$(date +%Y%m%d)"
mkdir -p "$DEST"
cp /opt/medical-chatbot/users.db "$DEST/"
cp -r /opt/medical-chatbot/faiss_index "$DEST/"
tar -czf "/backup/medical-chatbot/backup_$(date +%Y%m%d).tar.gz" "$DEST"
find /backup/medical-chatbot -name "backup_*.tar.gz" -mtime +30 -delete
```

Add to crontab:
```bash
0 2 * * * /opt/medical-chatbot/backup.sh
```

---

## Log Rotation

Create `/etc/logrotate.d/medical-chatbot`:
```
/var/log/medical-chatbot/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
    postrotate
        systemctl reload medical-chatbot
    endscript
}
```

---

## Monitoring

### Health endpoint

```bash
curl -sf https://your-domain.com/health
# {"status": "ok", "index_loaded": true}
```

### Metrics

```bash
curl -s https://your-domain.com/api/metrics \
  -H "Cookie: session=<admin-session>"
```

### Check for errors

```bash
grep "ERROR" /var/log/medical-chatbot/error.log | tail -50
grep "Failed login" /var/log/medical-chatbot/access.log
```

---

## Scaling

### Gunicorn workers

Rule of thumb: `workers = (2 × CPU cores) + 1`

The FAISS index and HuggingFace model are loaded once per worker process. With 4 workers on an 8GB machine, expect ~2GB per worker for the embedding model.

### Horizontal scaling

- Use `REDIS_URL` for shared rate-limit state across nodes
- Mount `faiss_index/` on shared storage (NFS/EFS) — it's read-only at runtime
- Use `docker-compose.production.yml` (PostgreSQL) for a proper multi-instance DB

### Auto-reindex watcher

To auto-rebuild the index when PDFs are added to `Data/`:
```bash
python auto_reindex_watcher.py &
```

Or add as a second systemd service unit pointing to the same virtualenv.

---

## CI/CD Pipeline

The GitHub Actions pipeline in `.github/workflows/ci-cd.yml` handles:

- **Lint**: flake8, black, isort
- **Security scan**: bandit, safety
- **Tests**: pytest with coverage upload to Codecov
- **Docker build**: multi-stage image pushed to ghcr.io with Trivy scan
- **Deploy staging**: SSH deploy on `develop` branch push
- **Deploy production**: SSH deploy on `main` push (requires approval in GitHub Environments)

Production deploys include a 60-second health-check loop (`/health`) and automatic rollback to the previous image if it fails.

Required GitHub secrets:
```
STAGING_HOST  STAGING_USER  STAGING_SSH_KEY
PROD_HOST     PROD_USER     PROD_SSH_KEY
SECRET_KEY    CODECOV_TOKEN
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Service fails to start | `journalctl -u medical-chatbot -n 50` |
| 502 Bad Gateway | Check gunicorn is running: `systemctl status medical-chatbot` |
| Streaming stops mid-response | Verify `proxy_buffering off` in nginx for `/get` |
| Rate limit 429 in dev | Increase limits in `app.py` or use `FLASK_ENV=development` |
| High memory usage | Reduce gunicorn workers in systemd unit |
| Index not reloading after reindex | Check `/admin/reindex` returned `success: true`; verify logs |
