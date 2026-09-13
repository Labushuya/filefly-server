# FileFly Server — Deploy via HomeNexus / hubctl

FileFly is a **compose-image-app**: the Pi pulls a prebuilt image from GHCR, and
`hubctl.ps1` (run from your DEV machine) prepares the stack, state, `.env`, and
starts it over SSH. No `git clone` on the Pi, no manual file copying.

This is the standard, manifest-driven path — FileFly ships a `.hubctl.json` and a
compose template, so hubctl discovers and bootstraps it generically.

---

## Prerequisites

- HomeNexus/hubctl set up (`misc/hubctl.ps1`, SSH key installed on the Pi).
- Repo present locally under a scanned DEV root (e.g. `H:\DEV\github\filefly-server`).
- Pi reachable at `ambersador@192.168.178.123` with Docker + Compose v2.
- Media HDD mounted at `/srv/hubdata/media` (uploads go to `/srv/hubdata/media/filefly`).

---

## Step 0 — Container image (already published)

FileFly's image is already built and published to GHCR as
`ghcr.io/labushuya/filefly-server:v0.1.4` (and `:latest`), multi-arch
(amd64 + arm64 — arm64 is what the Pi needs). **You do not need to tag anything.**

To publish a *future* release, bump the version and push a new tag:

```bash
# only for a NEW release, on your DEV machine
git tag v0.2.0
git push origin v0.2.0
```

The "Release" workflow then builds and pushes the new multi-arch image.

> Note: tags `v0.1.0`–`v0.1.3` were failed build attempts and have no image.
> `v0.1.4` is the first good one. If you created a local `v0.1.0` tag by hand,
> drop it with `git tag -d v0.1.0`.

**One thing you must still do:** make the GHCR package **public** so the Pi pulls
without a login — GitHub → your profile → Packages → `filefly-server` →
Package settings → Change visibility → **Public**.

---

## Step 1 — Bootstrap via hubctl

```powershell
# on your DEV machine
cd C:\Code\claude\misc
.\hubctl.ps1
```

- FileFly appears in the app list as a `compose-image-app` (discovered via `.hubctl.json`).
- Open its app menu → **Bootstrap**. hubctl then, over SSH:
  - writes the stack to `/srv/hubdata/stacks/filefly/docker-compose.yml`,
  - renders `.env` into `/srv/hubdata/state/filefly/.env` with a freshly generated
    `SECRET_KEY` (the `__GENERATE_HEX32__` sentinel from `.env.example`),
  - pulls the image, creates the media/state dirs, and starts the container.

> The `SECRET_KEY` is generated **on the Pi** and never leaves it. No secret in Git,
> none on your DEV machine.

---

## Step 2 — Get the one-time admin bootstrap code

On first start (empty DB), the server logs a single admin invite once:

```bash
ssh ambersador@192.168.178.123 \
  "docker compose -f /srv/hubdata/stacks/filefly/docker-compose.yml logs filefly"
```

Look for:

```
====================================================================
 FileFly bootstrap admin invite (shown ONCE, valid 24h, single use):

     <YOUR-CODE>

 Redeem it in the FileFly app now. It is not recoverable.
====================================================================
```

Lost it? `docker compose down`, remove the state DB dir
(`/srv/hubdata/state/filefly/data`), bootstrap again → new code.

---

## Step 3 — Verify & connect the app

```bash
curl http://192.168.178.123:8000/health      # from any LAN host
```

In the FileFly Android app: Server URL `http://192.168.178.123:8000`, then redeem
the bootstrap code → you are admin. Continue in the app's `TESTING.md`.

---

## Updates

```powershell
# hubctl → FileFly → Update: docker pull + compose up -d --force-recreate
```
State (`/srv/hubdata/state/filefly`) and uploads (`/srv/hubdata/media/filefly`) are
preserved across updates.

---

## Later: expose via Traefik at `https://filefly.fam.ily`

The test phase publishes plain `http` on port 8000. To integrate with your Traefik
reverse proxy: enable the commented Traefik/`proxy`-network block in
`deploy/docker-compose.fam.ily.yml`, remove the `ports:` mapping, add the Pi-hole
DNS record `filefly.fam.ily → 192.168.178.123`, and re-bootstrap. The app's server
URL then becomes `https://filefly.fam.ily` (the client must trust your fam.ily CA).

---

## Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `exec format error` on the Pi | Image not arm64 → ensure the release built multi-arch (Step 0) |
| Container exits, log says `SECRET_KEY` | `.env` not rendered → check `/srv/hubdata/state/filefly/.env` has a real key, not `__GENERATE_HEX32__` |
| `denied` / `unauthorized` on pull | GHCR package not public → make it public or `docker login ghcr.io` on the Pi |
| Uploads fail, permission denied | `/srv/hubdata/media` not mounted or wrong perms |
| Config change ignored | hubctl Update, or `docker compose up -d --force-recreate` |
