# Deployment Guide — Traefik + Docker + Pi-hole

This guide walks through deploying **FileFly Server** on a Raspberry Pi (or any Linux host) that already runs **Docker**, **Traefik** as a reverse proxy, and **Pi-hole** as local DNS. It covers storage, the Traefik integration, a local DNS record, a production `.env`, first admin bootstrap, health checks, updates, and troubleshooting.

> **Placeholders — adapt to your setup.** This guide uses the example IP `192.168.178.123` and hostname `filefly.home`. Replace both with your own Pi's LAN IP and your chosen local hostname everywhere they appear.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Raspberry Pi (or Linux host) | With Docker Engine + Compose plugin installed |
| Docker | 24+ · verify with `docker compose version` |
| Traefik | Already running as your reverse proxy, attached to a shared Docker network (commonly `traefik` or `proxy`) |
| Pi-hole | Running as the LAN's DNS resolver |
| Mounted storage | An HDD/SSD mounted on the host, e.g. `/mnt/data` |

Verify the basics:

```bash
docker compose version
docker network ls | grep -E "traefik|proxy"   # the network your Traefik uses
ls -ld /mnt/data                                # your mounted storage
```

---

## 1. Prepare storage

FileFly writes all uploads under `STORAGE_ROOT` (inside the container: `/data`). Point that at a directory on your mounted disk and make sure the container can write to it.

```bash
# Create the uploads directory on the mounted HDD
sudo mkdir -p /mnt/data/filefly/uploads

# The image runs as root by default, so root ownership is fine.
# If you run the container as a non-root UID, chown to that UID instead:
# sudo chown -R 1000:1000 /mnt/data/filefly

# Verify the mount is actually mounted (not writing to the SD card!)
mountpoint /mnt/data && echo "OK: /mnt/data is a real mount"
```

> **Watch the mount.** If `/mnt/data` is *not* mounted when the container starts, uploads land on the Pi's SD card and vanish/fill it up. Always confirm `mountpoint` before starting.

FileFly stages incomplete uploads in `<STORAGE_ROOT>/.filefly_tmp/<upload_id>/` and cleans them up on `complete`. The SQLite state DB (`filefly.db`) is separate — keep it on a persistent path too (see the compose file below).

---

## 2. Choose your access model

Two ways to reach the server on your LAN:

- **(a) Plain LAN — IP or local hostname, no TLS.** Simplest. You hit `http://192.168.178.123:8000` directly, or map a Pi-hole hostname to the IP. Good enough for a trusted home network; the app talks plain HTTP.
- **(b) Behind Traefik with a local hostname.** Traefik routes `http(s)://filefly.home` to the container. You get a clean hostname, no exposed port, and optional TLS. Recommended if you already run Traefik.

You can do both: expose port `8000` for direct access *and* add Traefik labels. The sections below cover option (b) in full; option (a) is just the compose file without the Traefik labels (keep the `ports:` mapping).

---

## 3. docker-compose with Traefik integration

Create `docker-compose.yml` on the Pi (or adapt the one in the repo). This example wires the container into Traefik via labels and keeps state on the mounted disk.

```yaml
services:
  filefly-server:
    image: ghcr.io/labushuya/filefly-server:latest   # or build: . from the repo
    container_name: filefly-server
    restart: unless-stopped
    env_file: .env
    volumes:
      - /mnt/data/filefly/uploads:/data
      - /mnt/data/filefly/filefly.db:/app/filefly.db
    # Option (a): direct LAN access — keep this for IP/host:8000 without Traefik.
    # Remove it if you only want access through Traefik.
    ports:
      - "8000:8000"
    networks:
      - proxy            # the shared network Traefik is attached to
    labels:
      - "traefik.enable=true"
      # --- Router: match the local hostname ---
      - "traefik.http.routers.filefly.rule=Host(`filefly.home`)"
      - "traefik.http.routers.filefly.entrypoints=web"          # 'web' = :80
      # --- Service: which port inside the container to forward to ---
      - "traefik.http.services.filefly.loadbalancer.server.port=8000"
      # --- Bind router → service (needed when several services exist) ---
      - "traefik.http.routers.filefly.service=filefly"

networks:
  proxy:
    external: true       # created/owned by your Traefik stack
```

Notes:

- `image:` — pull a published image if you have one, or replace with `build: .` and run `docker compose build` from a checkout of the repo.
- The DB bind mount (`filefly.db`) must point at a file path; create an empty file first if the bind fails on start: `touch /mnt/data/filefly/filefly.db`.
- `networks.proxy.external: true` assumes Traefik and FileFly share a pre-existing Docker network. Match the name to whatever your Traefik uses (`docker network ls`).

### Optional: TLS via Traefik

LAN-only deployments usually run plain HTTP — it is the pragmatic default here. If you want HTTPS on a local hostname, Traefik can terminate TLS with either a certificate you provide or an internal resolver. A minimal HTTPS router:

```yaml
      - "traefik.http.routers.filefly.entrypoints=websecure"    # 'websecure' = :443
      - "traefik.http.routers.filefly.tls=true"
      # If you use an ACME/DNS resolver configured in Traefik:
      # - "traefik.http.routers.filefly.tls.certresolver=myresolver"
```

For a purely internal name like `filefly.home`, public ACME (Let's Encrypt HTTP-01) will not validate — use a **self-signed / internal CA cert** loaded into Traefik, or a DNS-01 resolver for a real domain you own. If that is more than you need, stick with plain HTTP on the LAN.

---

## 4. Pi-hole local DNS record

To use `filefly.home` instead of the raw IP, add a local A-record in Pi-hole so the hostname resolves to the Pi.

1. Open the Pi-hole admin UI (`http://<pi-hole-ip>/admin`).
2. Go to **Local DNS → DNS Records**.
3. Add a record:
   - **Domain:** `filefly.home`
   - **IP Address:** `192.168.178.123`  *(your Pi's LAN IP)*
4. Click **Add**.

Now every device that uses Pi-hole as its DNS resolver will resolve `filefly.home` to the Pi. Verify from another machine:

```bash
nslookup filefly.home
# Should return 192.168.178.123
```

> Clients must actually use Pi-hole for DNS (via your router's DHCP settings or a per-device DNS override). Devices with hard-coded public DNS (8.8.8.8, etc.) will not see this record.

---

## 5. How the Traefik router works

The labels in step 3 tell Traefik three things:

| Label | Purpose |
|---|---|
| `traefik.http.routers.filefly.rule=Host(\`filefly.home\`)` | Match incoming requests whose `Host` header is `filefly.home` and hand them to this router. |
| `traefik.http.routers.filefly.entrypoints=web` | Which Traefik entrypoint (port) accepts them — `web` is typically `:80`, `websecure` `:443`. |
| `traefik.http.services.filefly.loadbalancer.server.port=8000` | The container's internal port Traefik forwards to (FileFly listens on `8000`). |

Request flow: **client → `filefly.home` (resolved by Pi-hole to the Pi) → Traefik `:80` → router matches Host → service forwards to container `:8000`**.

Reload behaviour: Traefik watches the Docker socket and picks up label changes automatically when the container is (re)created. After editing labels, run `docker compose up -d --force-recreate` (see step 9) so the container is recreated with the new labels.

---

## 6. Production `.env`

Copy the example and set real values. **Never leave the default `SECRET_KEY` in production** — it is public knowledge and would let anyone forge admin tokens. The server **refuses to start** while `SECRET_KEY` is unset or still the default.

```bash
cp .env.example .env
```

```dotenv
# Storage root inside the container (matches the /data volume mount)
STORAGE_ROOT=/data

# JWT signing key — REQUIRED. Generate a fresh one:  openssl rand -hex 32
# The server will not start with the default/empty value.
SECRET_KEY=<output of: openssl rand -hex 32>

# Token lifetime in hours (default 7 days)
JWT_EXPIRE_HOURS=168

# Max size of a single upload chunk (MB)
MAX_CHUNK_SIZE_MB=10

# CORS origins. '*' is fine for a trusted LAN; restrict if you want.
ALLOWED_ORIGINS=*
```

Generate the secret:

```bash
openssl rand -hex 32
```

> **Security note.** There is no admin password in `.env`. On the **first** start (empty database) the server generates a single, random, one-time admin invite and prints it **once** to the logs (see step 7). It expires after 24 hours and is consumed on first use. Invite codes are stored only as SHA-256 hashes — never in clear text. Treat `SECRET_KEY` like a password and never commit `.env`.

---

## 7. First start & admin bootstrap

Start the stack and grab the one-time admin invite from the logs.

```bash
docker compose up -d
docker compose logs filefly-server   # the bootstrap invite is printed once, near the top
```

On the **first** start you will see a boxed message like:

```
====================================================================
 FileFly bootstrap admin invite (shown ONCE, valid 24h, single use):

     xB3kf9_Qz1...             <-- your code

 Redeem it in the FileFly app now. It is not recoverable.
====================================================================
```

Copy that code. Redeem it to get an admin JWT (works via IP or, once DNS is set, the hostname):

```bash
curl -s -X POST http://filefly.home/auth/invite/validate \
  -H "Content-Type: application/json" \
  -d '{"code":"<the bootstrap code from the logs>"}'
```

Response contains `access_token` (the JWT), plus `role`, `base_path`, and `permissions`. Save the token:

```bash
TOKEN="<access_token from the response>"
```

Now create scoped invites for the other roles. `base_path` is relative to `STORAGE_ROOT`.

```bash
# A USER invite scoped to /data/photos (upload, mkdir, rename — no delete)
curl -s -X POST http://filefly.home/auth/invite \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"role":"user","base_path":"photos"}'

# A SERVICE invite (upload only) for an automated backup job
curl -s -X POST http://filefly.home/auth/invite \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"role":"service","base_path":"backups"}'

# A GUEST invite that expires and is limited to 3 uses
curl -s -X POST http://filefly.home/auth/invite \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"role":"guest","base_path":"dropbox","max_uses":3,"expires_at":"2026-12-31T23:59:59Z"}'
```

Each response returns the generated `code`. Hand that code to the person or app, which redeems it via `/auth/invite/validate` to get its own token. List or revoke invites any time:

```bash
curl -s http://filefly.home/auth/invites   -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE http://filefly.home/auth/invite/<code> -H "Authorization: Bearer $TOKEN"
```

---

## 8. Health check & verification

```bash
# Liveness
curl -s http://filefly.home/health     # -> {"status":"ok"}

# Version
curl -s http://filefly.home/version    # -> {"version":"0.1.0"}

# Interactive API docs in a browser
# http://filefly.home/docs
```

If those work over the hostname, DNS + Traefik + container are all wired correctly. If they only work over `http://192.168.178.123:8000` but not the hostname, the problem is DNS (Pi-hole) or Traefik routing, not FileFly.

---

## 9. Updating

```bash
cd /path/to/your/filefly-stack

# Pull the new image (or rebuild from a fresh checkout)
docker compose pull            # if using a published image
# docker compose build         # if using build: .

# Recreate the container
docker compose up -d --force-recreate
```

> **Use `--force-recreate` when config changes.** A plain `restart` reuses the old container with its old environment and labels. If you changed `.env`, volume mounts, or Traefik labels, you **must** recreate the container for the new values to take effect — a `restart` alone will silently keep the old config. When only the image changed, `docker compose up -d` recreates as needed; `--force-recreate` is the safe default when in doubt.

Verify with the health check (step 8) after the update.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Uploads fail with permission errors, or `complete` cannot write | Container can't write to the mounted directory | Check ownership of `/mnt/data/filefly/uploads`; `chown` to the container's UID or run as root. Confirm `mountpoint /mnt/data`. |
| Files appear then vanish / SD card fills up | `STORAGE_ROOT` is not on the mounted disk (mount wasn't ready at start) | Ensure the HDD is mounted *before* Docker starts; verify with `mountpoint`. Restart the stack after mounting. |
| `filefly.home` doesn't resolve | Pi-hole record missing, or client not using Pi-hole for DNS | Re-check **Local DNS → DNS Records**; run `nslookup filefly.home`. Point the device/router DNS at Pi-hole. |
| Hostname resolves but returns 404 / Traefik default page | Traefik label typo or wrong network | Check `Host(...)` rule spelling, the `loadbalancer.server.port=8000`, and that the container is on the same Docker network as Traefik (`docker network inspect`). |
| Traefik never picks up label changes | Container not recreated | `docker compose up -d --force-recreate` (see step 9). |
| Stale DNS / old IP still cached | Pi-hole or client DNS cache | Flush Pi-hole (`pihole restartdns`) and the client's DNS cache; re-test `nslookup`. |
| `401 Invalid token` on every request | Wrong/missing bearer header, or `SECRET_KEY` changed after token was issued | Send `Authorization: Bearer <jwt>`. Changing `SECRET_KEY` invalidates all existing tokens — re-redeem invites. |
| `403 Path traversal not allowed` | Path escaped the invite's `base_path` (contains `../`) | Use paths relative to the invite's base directory; traversal is blocked by design. |
| `413 Chunk too large` | Chunk exceeds `MAX_CHUNK_SIZE_MB` | Lower the client's chunk size or raise `MAX_CHUNK_SIZE_MB` and recreate the container. |

---

## Reference

- Endpoints, roles, and configuration: see the project [README](../README.md).
- Manual QA checklist: [docs/test-manifest.html](test-manifest.html).
