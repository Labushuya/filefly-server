<div align="center">
  <img src="https://img.shields.io/badge/FileFly-Server-4A90D9?style=for-the-badge&logo=server&logoColor=white" alt="FileFly Server" height="60"/>
  <br/><br/>

  [![GitHub Release](https://img.shields.io/github/v/release/Labushuya/filefly-server?style=flat-square)](https://github.com/Labushuya/filefly-server/releases)
  [![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
  [![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)
  [![CI](https://img.shields.io/github/actions/workflow/status/Labushuya/filefly-server/ci.yml?style=flat-square&label=CI)](https://github.com/Labushuya/filefly-server/actions)
</div>

# FileFly Server

Self-hosted file upload server for the [FileFly Android app](https://github.com/Labushuya/filefly). Designed for local network use — fast chunked uploads, invite-based access control, and zero external dependencies.

---

## Features

- **Chunked uploads** — large files split and reassembled reliably, with progress tracking
- **Invite system** — share access via short codes; each invite carries role + directory + permissions
- **4 roles** — Admin, User, Service, Guest with fine-grained permission scopes
- **Conflict handling** — overwrite, auto-rename, or skip on filename clash
- **Path safety** — all paths validated against invite's base directory; traversal blocked
- **LAN-only** — no authentication beyond invite codes, designed for trusted home networks
- **Docker-ready** — single `docker-compose up` on your Raspberry Pi

---

## Quick Start

### Requirements

- Docker + Docker Compose
- Raspberry Pi (or any Linux host) with a mounted HDD

### Deploy

```bash
# Clone
git clone https://github.com/Labushuya/filefly-server.git
cd filefly-server

# Configure
cp .env.example .env
nano .env   # Set SECRET_KEY and ADMIN_INVITE_CODE

# Start
docker compose up -d
```

The server starts on port `8000`. Access it from any device on your local network.

### First Login

Use the `ADMIN_INVITE_CODE` you set in `.env` to authenticate from the FileFly app. This grants full admin access to create further invites.

---

## API Overview

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/invite/validate` | Redeem invite code, receive JWT |
| `POST` | `/auth/invite` | Create invite (Admin) |
| `GET` | `/auth/invites` | List invites (Admin) |
| `DELETE` | `/auth/invite/{code}` | Delete invite (Admin) |
| `GET` | `/files/list?path=` | List directory |
| `POST` | `/files/upload/init` | Start upload session |
| `POST` | `/files/upload/chunk` | Upload a chunk |
| `POST` | `/files/upload/complete` | Finalize upload |
| `POST` | `/files/mkdir` | Create directory |
| `POST` | `/files/rename` | Rename entry |
| `DELETE` | `/files/delete` | Delete entry |
| `GET` | `/health` | Health check |
| `GET` | `/version` | Server version |

Interactive docs: `http://<your-pi-ip>:8000/docs`

---

## Roles

| Role | Upload | mkdir | rename | delete | Invite Mgmt | Notes |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ | Full access, root directory |
| **User** | ✅ | ✅ | ✅ | ❌ | ❌ | Fixed base directory from invite |
| **Service** | ✅ | ❌ | ❌ | ❌ | ❌ | Automated upload only |
| **Guest** | ✅ | ❌ | ❌ | ❌ | ❌ | Temporary, expires with invite |

---

## Configuration

All settings via environment variables or `.env`:

| Variable | Default | Description |
|---|---|---|
| `STORAGE_ROOT` | `/data` | Root directory for all uploads |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **change this** |
| `ADMIN_INVITE_CODE` | `admin-setup` | Bootstrap invite for first admin |
| `JWT_EXPIRE_HOURS` | `168` | Token lifetime (7 days) |
| `MAX_CHUNK_SIZE_MB` | `10` | Max size per upload chunk |
| `ALLOWED_ORIGINS` | `*` | CORS origins (comma-separated) |

---

## Roadmap

### v0.1 — Foundation ✅
- [x] FastAPI server scaffold
- [x] Invite system with 4 roles
- [x] Chunked upload with conflict handling
- [x] Path traversal protection
- [x] Docker + docker-compose
- [x] CI/CD via GitHub Actions

### v0.2 — Stability
- [ ] Upload session cleanup (stale sessions)
- [ ] Upload resume (re-send missing chunks)
- [ ] Rate limiting per invite
- [ ] Structured logging

### v0.3 — Operations
- [ ] Web UI for admin invite management
- [ ] Storage quota per invite
- [ ] Upload history endpoint
- [ ] Webhook on upload complete

### v1.0 — Production
- [ ] HTTPS support (Let's Encrypt / self-signed)
- [ ] Invite expiry notifications
- [ ] Multi-storage backend (local + S3-compatible)

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Tests:

```bash
pytest tests/ -v
```

---

## License

MIT © [Labushuya](https://github.com/Labushuya)
