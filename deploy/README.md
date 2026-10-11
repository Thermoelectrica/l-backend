# Plain VM deployment (systemd)

An alternative to the Yandex Cloud serverless container: run the backend as a
regular systemd service on a VM.

| File | Purpose |
|------|---------|
| `l-inspector-backend.service` | systemd unit — uvicorn serving `app.main:app` on `0.0.0.0:8080` |
| `setup_vm.sh` | Idempotent install/update script, run as root from a repository checkout |

## Layout on the VM

```
/opt/l-inspector-backend/
├── app/               # application code (copied by setup_vm.sh)
├── .venv/             # virtualenv with pinned dependencies (requirements.txt)
└── .env               # configuration (never overwritten by re-runs)

/etc/systemd/system/l-inspector-backend.service
```

The service runs as the dedicated system user `l-inspector` (no login shell).

## First install

Get the code onto the VM (git clone, or rsync/scp a working copy), then:

```bash
cd l-backend
sudo ./deploy/setup_vm.sh
```

The script installs Python 3 if needed, deploys the code, creates the venv,
installs and enables the unit. On first run it does **not** start the service:
it creates `/opt/l-inspector-backend/.env` from `.env.example` and prints the
next steps (edit `.env`, migrate DB, start).

## Configuration

All settings live in `/opt/l-inspector-backend/.env` (full list in
`.env.example`). Required for production:

| Variable | Notes |
|----------|-------|
| `DATABASE_URL` | PostgreSQL host/port/db. The VM must have network access to it (same VPC / security groups as the serverless revision). |
| `DATABASE_PASSWORD` | Kept separately from the URL, same as in the serverless deployment. |
| `S3_BUCKET_NAME`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Yandex Object Storage for images. |
| `PRIVATE_KEY` / `PUBLIC_KEY` | RSA keys for JWT: single line with `\n` escapes inside double quotes (see `.env.example`), or use `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` pointing to `.pem` files. |

Notes:

- `DB_DRIVER` defaults to `asyncpg` — correct for a VM. The `psycopg2` mode is
  only for serverless/Mangum.
- The same `.env` is read both by systemd (`EnvironmentFile=`) and by the
  application itself (pydantic-settings), so there is one source of truth.
- After editing `.env`, restart: `sudo systemctl restart l-inspector-backend`.
- Set `LOG_JSON=false` if you prefer plain-text logs in journald (default is
  structured JSON, same as the container deployment).

## Database migrations

The script does **not** run Flyway migrations — normally they are applied by CI
(`deploy.yml`). For a database that is not migrated yet (or if this VM becomes
the migration runner), run them once:

```bash
wget -qO- https://download.red-gate.com/maven/release/com/redgate/flyway/flyway-commandline/12.0.1/flyway-commandline-12.0.1-linux-x64.tar.gz \
  | tar -xz -C "$HOME"
export PATH="$HOME/flyway-12.0.1/bin:$PATH"

cd db
FLYWAY_URL="jdbc:postgresql://<host>:<port>/<db>" \
FLYWAY_USER=<user> \
FLYWAY_PASSWORD=<password> \
flyway migrate
```

## Updating

```bash
cd l-backend && git pull        # or copy/rsync a new revision of the repo
sudo ./deploy/setup_vm.sh       # re-deploys code + deps, restarts the service
```

The existing `.env` is preserved. To roll back: `git checkout <tag>` and re-run
the script.

## Operations

```bash
systemctl status l-inspector-backend         # service state
journalctl -u l-inspector-backend -f         # live logs
curl http://127.0.0.1:8080/                  # health check (public endpoint)
sudo systemctl restart l-inspector-backend   # after .env changes
```

To change the port (default 8080), use a systemd drop-in instead of editing the
installed unit:

```bash
sudo systemctl edit l-inspector-backend
```

```ini
[Service]
ExecStart=
ExecStart=/opt/l-inspector-backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 9000
```

```bash
sudo systemctl restart l-inspector-backend
```

## Firewall / TLS

Open the port (8080) in the cloud security groups and/or the host firewall.
Prefer putting the backend behind a reverse proxy (nginx, Yandex ALB) for TLS
termination — the service itself serves plain HTTP.
