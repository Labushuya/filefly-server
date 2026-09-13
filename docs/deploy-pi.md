# FileFly Server — Deploy auf den Raspberry Pi (LAN, IP:Port)

Konkretes Runbook für **deinen** Setup: Windows-Laptop → SSH → Pi `ambersador@192.168.178.123`.
Erststart im einfachen LAN-Modus (`http://192.168.178.123:8000`), Git-Pull + Build direkt auf dem Pi.
Traefik/Hostname/TLS kommt später (eigener Abschnitt am Ende).

> Legende: `#pc` = im Git-Bash/CMD auf dem Laptop, `#pi` = in der SSH-Session auf dem Pi.

---

## 0. Voraussetzung: Repo auf den Pi bringen

Dein Repo liegt lokal (`H:\DEV\github\filefly-server`) und auf GitHub. Der Pi zieht es direkt von GitHub — nichts vom Laptop kopieren nötig.

```bash
#pc  — SSH öffnen
ssh ambersador@192.168.178.123
```

```bash
#pi  — Ablageort wählen (passe an dein Muster an; hier ~/docker)
mkdir -p ~/docker && cd ~/docker
git clone https://github.com/Labushuya/filefly-server.git
cd filefly-server
```

> Falls schon geklont: `cd ~/docker/filefly-server && git pull`.

---

## 1. Pre-Flight-Checks (kollidiert FileFly mit Bestehendem?)

```bash
#pi
uname -m                                    # arm64/aarch64 erwartet (Pi 3/4/5 64-bit)
docker --version && docker compose version  # Compose v2 (Leerzeichen) muss da sein

# Ist Port 8000 frei? (darf NICHTS ausgeben)
sudo ss -tlnp | grep ':8000' && echo "!! 8000 BELEGT — anderen Port wählen (Schritt 3)" || echo "8000 frei"

# Läuft schon was Relevantes?
docker ps --format 'table {{.Names}}\t{{.Ports}}'
```

Wenn **8000 belegt** ist: im nächsten Schritt in `docker-compose.yml` z.B. `"8080:8000"` statt `"8000:8000"` — dann ist FileFly unter `:8080` erreichbar (App-URL entsprechend anpassen).

---

## 2. Storage vorbereiten (die HDD)

FileFly schreibt Uploads nach `/data` im Container, gemountet von `/mnt/data` auf dem Pi.

```bash
#pi
# Wo ist deine HDD gemountet? (anpassen falls anders als /mnt/data)
df -h | grep -iE 'mnt|media'
lsblk

# Zielverzeichnis anlegen + beschreibbar machen
sudo mkdir -p /mnt/data
sudo chown -R $USER:$USER /mnt/data       # oder passende Rechte für den Container-User
touch /mnt/data/.filefly-write-test && rm /mnt/data/.filefly-write-test && echo "schreibbar OK"
```

> Ist deine HDD woanders gemountet (z.B. `/media/usbhdd`)? Dann in `docker-compose.yml` die Volume-Zeile `- /mnt/data:/data` auf deinen Pfad ändern, z.B. `- /media/usbhdd/filefly:/data`.

**Wichtig (SQLite-DB-Mount):** Die DB wird als Datei gemountet. Lege sie VOR dem ersten Start an, sonst macht Docker daraus ein Verzeichnis und SQLite scheitert:
```bash
#pi
touch ~/docker/filefly-server/filefly.db
```

---

## 3. Secret + Config setzen (.env)

```bash
#pi
cd ~/docker/filefly-server
cp .env.example .env

# Starken JWT-Signaturschlüssel erzeugen und direkt in die .env schreiben:
SECRET=$(openssl rand -hex 32)
sed -i "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env

# Kontrolle (der Wert MUSS jetzt zufällig sein, nicht "change-me..."):
grep '^SECRET_KEY=' .env
```

> `.env` ist git-ignored — dieser Schlüssel bleibt nur auf dem Pi und landet nie in Git.
> Optional Port ändern (falls 8000 belegt): `nano docker-compose.yml` → `ports: - "8080:8000"`.

---

## 4. Starten + Admin-Bootstrap-Code holen

```bash
#pi
cd ~/docker/filefly-server
docker compose up -d --build          # baut das Image auf dem Pi (dauert beim 1. Mal einige Min)

docker compose ps                     # Status: sollte "running"/"healthy" sein
docker compose logs filefly-server    # >>> HIER steht dein einmaliger Admin-Code <<<
```

Im Log erscheint EINMALIG:
```
====================================================================
 FileFly bootstrap admin invite (shown ONCE, valid 24h, single use):

     <DEIN-CODE>

 Redeem it in the FileFly app now. It is not recoverable.
====================================================================
```
📋 **Code notieren.** 24 h / 1× gültig. Verloren? → `docker compose down && rm filefly.db && touch filefly.db && docker compose up -d` erzeugt einen neuen.

---

## 5. Erreichbarkeit testen

```bash
#pi  — lokal auf dem Pi
curl http://localhost:8000/health
curl http://localhost:8000/version
```
```bash
#pc  — vom Laptop (gleiches LAN)
curl http://192.168.178.123:8000/health
```
Beide sollten eine JSON-Antwort liefern. Wenn vom Laptop nichts kommt: Pi-Firewall (`sudo ufw status`) prüfen, ggf. Port 8000 freigeben.

Danach: **App** (`filefly-v0.3.0.apk`) → Onboarding → Server-URL `http://192.168.178.123:8000` + Bootstrap-Code. Weiter in `../filefly/docs/TESTING.md` Teil 3–5.

---

## 6. Betrieb: Updates & Wartung

```bash
#pi  — neue Version deployen
cd ~/docker/filefly-server
git pull
docker compose up -d --build --force-recreate   # --force-recreate: nötig wenn .env/Config/Labels sich änderten

# Logs live verfolgen
docker compose logs -f filefly-server

# Stoppen / entfernen (Daten auf /mnt/data + filefly.db bleiben erhalten)
docker compose down
```

---

## 7. Später: Integration in Traefik + Pi-hole (optional)

Wenn du von IP:Port auf einen sauberen Hostnamen (`https://filefly.home`) umstellen willst — die vollständige Anleitung mit Traefik-Labels und Pi-hole-DNS-Record steht in **`docs/setup.md`** (Abschnitte 3–5). Kurzfassung:
1. Pi-hole → Local DNS → DNS Records: `filefly.home` → `192.168.178.123`.
2. In `docker-compose.yml` die Traefik-Labels aus `docs/setup.md` ergänzen + FileFly ins Traefik-Docker-Netzwerk hängen (`networks:`), `ports:` kann dann entfallen.
3. `docker compose up -d --force-recreate`.
4. App-Server-URL auf `http://filefly.home` (bzw. `https://…` bei TLS) umstellen.

---

## Troubleshooting (Pi-spezifisch)

| Symptom | Ursache / Fix |
|---|---|
| `docker compose` → „command not found" | Alt-Syntax `docker-compose` (Bindestrich) oder Compose-Plugin fehlt → `sudo apt install docker-compose-plugin` |
| Container startet, dann „SECRET_KEY" im Log | `.env` nicht gesetzt/Default → Schritt 3 wiederholen, dann `--force-recreate` |
| `filefly.db` ist ein Verzeichnis geworden | DB-Datei vor 1. Start nicht ge`touch`t → `docker compose down; rm -rf filefly.db; touch filefly.db; docker compose up -d` |
| Upload scheitert, „permission denied" | Rechte auf `/mnt/data` → `sudo chown -R $USER:$USER /mnt/data` |
| Vom Laptop nicht erreichbar, vom Pi schon | Firewall (`sudo ufw allow 8000/tcp`) oder falsche IP |
| Port-Konflikt beim Start | 8000 belegt → anderen Host-Port in `ports:` (Schritt 1/3) |
| Build bricht mit arm-Fehler ab | Sehr alter 32-bit-Pi (armv7) → melden, dann Image/Base anpassen |
