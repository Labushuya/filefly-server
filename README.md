![FileFly](docs/banner.svg)

<div align="center">

[![GitHub Release](https://img.shields.io/github/v/release/Labushuya/filefly-server?style=flat-square)](https://github.com/Labushuya/filefly-server/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat-square)](https://python.org)

</div>

# FileFly Server

**A self-hosted, invite-based server for receiving files over your LAN — chunked, permission-scoped, and conflict-aware.**

FileFly Server is a small FastAPI application and a reusable pattern for running your own file-receiving endpoint on a home server. Point any client at it, hand out invite codes, and let people (or automated jobs) drop files into scoped directories on your storage — without exposing anything to the public internet.

It is deliberately generic: there is no hard-coded project, user, or storage layout. You define the roles and directories via invites, mount whatever storage you like, and run it behind your own reverse proxy. Use it as-is, or fork it as a starting point for your own upload service.

---

## Features

- **Chunked uploads** — large files are split into chunks, staged, and reassembled server-side (`init` → `chunk` → `complete`).
- **4 roles** — `admin`, `user`, `service`, `guest`, each with a default permission set (`upload`, `mkdir`, `rename`, `delete`, `invite`).
- **Invite links** — access is granted by short invite codes. Each invite carries a role, a base directory, a permission list, and optional expiry / max-uses.
- **Conflict handling** — on filename clash, choose `overwrite`, `rename` (auto-suffix), or `skip` per upload.
- **LAN-only by design** — no user database, no public sign-up; authentication is an invite code exchanged for a short-lived JWT. Meant for trusted local networks.
- **Path-traversal-safe** — every path is resolved against the invite's base directory; `../` escapes are rejected with `403`.
- **Docker-ready** — ships with a `Dockerfile` and `docker-compose.yml`; SQLite state, no external database.

---

## Quick Start (Docker)

```bash
# Clone
git clone https://github.com/Labushuya/filefly-server.git
cd filefly-server

# Configure
cp .env.example .env
# Edit .env — at minimum set SECRET_KEY and ADMIN_INVITE_CODE (see below)

# Start
docker compose up -d
```

The server listens on port `8000`. From any device on your LAN, open `http://<host-ip>:8000/docs` for the interactive OpenAPI UI, or `http://<host-ip>:8000/health` to check it is alive.

> **First run:** redeem the `ADMIN_INVITE_CODE` from your `.env` (via `POST /auth/invite/validate`) to receive an admin JWT, then create further invites for users, service accounts, and guests.

For a full deployment walkthrough — reverse proxy (Traefik), local DNS (Pi-hole), storage mounts, production `.env`, and updates — see **[docs/setup.md](docs/setup.md)**.

For the manual QA checklist, see **[docs/test-manifest.html](docs/test-manifest.html)**.

---

## API Overview

All `/files/*` and admin `/auth/*` endpoints require a bearer token: `Authorization: Bearer <jwt>`.

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/invite/validate` | none | Redeem an invite code, receive a JWT |
| `POST` | `/auth/invite` | admin | Create an invite |
| `GET` | `/auth/invites` | admin | List all invites |
| `DELETE` | `/auth/invite/{code}` | admin | Delete an invite |
| `GET` | `/files/list?path=` | token | List a directory |
| `POST` | `/files/upload/init` | token | Start a chunked upload session |
| `POST` | `/files/upload/chunk` | token | Upload one chunk (multipart) |
| `POST` | `/files/upload/complete` | token | Reassemble chunks into the final file |
| `POST` | `/files/mkdir` | token + `mkdir` | Create a directory |
| `POST` | `/files/rename` | token + `rename` | Rename a file or directory |
| `DELETE` | `/files/delete` | token + `delete` | Delete a file or directory |
| `GET` | `/health` | none | Liveness check → `{"status":"ok"}` |
| `GET` | `/version` | none | Server version |

Interactive docs (Swagger UI) are served at `/docs`.

---

## Roles

Roles map to a default permission set. An invite may also carry an explicit `permissions` list that overrides the default. "Admin" is determined by holding the `invite` permission, not by the role name alone.

| Role | `upload` | `mkdir` | `rename` | `delete` | `invite` | Typical use |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **admin** | ✅ | ✅ | ✅ | ✅ | ✅ | Full access, manages invites |
| **user** | ✅ | ✅ | ✅ | ❌ | ❌ | Person with a scoped base directory |
| **service** | ✅ | ❌ | ❌ | ❌ | ❌ | Automated upload-only job |
| **guest** | ✅ | ❌ | ❌ | ❌ | ❌ | Temporary drop, typically with expiry / max-uses |

Note: `/files/list` requires only the `upload` permission — every authenticated invite can list the directories it is allowed to upload to. `delete` is intentionally excluded from the `user` default.

---

## Configuration

Set via environment variables or a `.env` file:

| Variable | Default | Description |
|---|---|---|
| `STORAGE_ROOT` | `/data` | Root directory for all uploads |
| `SECRET_KEY` | `change-me-in-production` | JWT signing key — **change this in production** |
| `ADMIN_INVITE_CODE` | `admin-setup` | Bootstrap invite for the first admin — **change this** |
| `JWT_EXPIRE_HOURS` | `168` | Token lifetime in hours (7 days) |
| `MAX_CHUNK_SIZE_MB` | `10` | Maximum size of a single upload chunk |
| `ALLOWED_ORIGINS` | `*` | CORS origins (comma-separated) |
| `DB_PATH` | `filefly.db` | Path to the SQLite state database |

---

## Companion app

FileFly Server pairs with the **[FileFly Android app](https://github.com/Labushuya/filefly)**, which redeems an invite code and uploads files with chunking and conflict handling. The server is standalone, though — any HTTP client that speaks the API above works.

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Run the tests:

```bash
pytest tests/ -v
```

---

## Contributing

Contributions are welcome. Please open an issue to discuss significant changes before submitting a pull request, keep changes focused, and run `ruff` and `pytest` before pushing.

---

## License

MIT © [Labushuya](https://github.com/Labushuya)
