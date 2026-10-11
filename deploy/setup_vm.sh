#!/usr/bin/env bash
# =============================================================================
# setup_vm.sh — deploy L-Inspector backend to a plain VM (Debian/Ubuntu/RHEL)
#
# What it does:
#   1. Installs Python 3 with venv support (and curl) if missing
#   2. Creates a dedicated system user "l-inspector"
#   3. Deploys the application to /opt/l-inspector-backend
#      (code + virtualenv; an existing .env is never overwritten)
#   4. Installs and enables the systemd service l-inspector-backend.service
#   5. Restarts the service and runs a health check against GET /
#
# The script is idempotent: re-run it after `git pull` (or after copying a new
# revision of the repo to the VM) to update code, dependencies and the service.
#
# Usage (from a repository checkout on the VM):
#   sudo ./deploy/setup_vm.sh
#
# NOTE: database migrations (Flyway) are NOT run by this script — they are
# applied by CI (deploy.yml) or manually, see deploy/README.md.
# =============================================================================
set -euo pipefail

# ── Configuration (paths and user must match l-inspector-backend.service) ────
APP_NAME="l-inspector-backend"
APP_DIR="/opt/l-inspector-backend"
SERVICE_USER="l-inspector"
SERVICE_FILE="${APP_NAME}.service"
PORT="8080"  # only used for the post-install health check

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { printf '[setup] %s\n' "$*"; }
warn() { printf '[setup] WARNING: %s\n' "$*" >&2; }
die()  { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

# ── Preflight ────────────────────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "This script must be run as root: sudo ./deploy/setup_vm.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

[[ -d "$REPO_DIR/app" ]]              || die "Directory not found: $REPO_DIR/app — run this script from a repository checkout."
[[ -f "$REPO_DIR/requirements.txt" ]] || die "File not found: $REPO_DIR/requirements.txt — run this script from a repository checkout."
[[ -f "$SCRIPT_DIR/$SERVICE_FILE" ]]  || die "File not found: $SCRIPT_DIR/$SERVICE_FILE — the unit file must sit next to this script."

# ── 1. System packages ───────────────────────────────────────────────────────
# python3-venv is a separate package on Debian/Ubuntu; curl is used for the
# health check at the end.
if ! python3 -c "import venv, ensurepip" >/dev/null 2>&1; then
    log "Installing Python 3 (with venv) and curl..."
    if command -v apt-get >/dev/null 2>&1; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -y
        apt-get install -y python3 python3-venv curl
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y python3 curl
    else
        die "Python 3 with venv support is required, but neither apt-get nor dnf is available."
    fi
fi

python3 -c "import venv, ensurepip" >/dev/null 2>&1 \
    || die "Python 3 with venv support is required (Debian/Ubuntu: apt install python3 python3-venv)."

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
    || die "Python 3.10 or newer is required, found: $(python3 --version 2>&1)."

# ── 2. Service user ──────────────────────────────────────────────────────────
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    log "Creating system user '$SERVICE_USER'..."
    useradd --system --home-dir "$APP_DIR" --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

# ── 3. Deploy application code ───────────────────────────────────────────────
log "Deploying application code to $APP_DIR ..."
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/app"
cp -a "$REPO_DIR/app" "$APP_DIR/app"
cp "$REPO_DIR/requirements.txt" "$APP_DIR/requirements.txt"

# ── 4. Environment file (.env) ───────────────────────────────────────────────
FRESH_ENV=0
if [[ ! -f "$APP_DIR/.env" ]]; then
    FRESH_ENV=1
    if [[ -f "$REPO_DIR/.env.example" ]]; then
        cp "$REPO_DIR/.env.example" "$APP_DIR/.env"
        log "Created $APP_DIR/.env from .env.example (unconfigured template)."
    else
        warn "$APP_DIR/.env does not exist and no .env.example was found in the repo."
    fi
fi

# ── 5. Virtualenv + dependencies ─────────────────────────────────────────────
log "Installing Python dependencies (this can take a minute)..."
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
    python3 -m venv "$APP_DIR/.venv"
fi
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" \
    || die "pip install failed. requirements.txt is pinned with --only-binary :all: — this VM's Python version may have no prebuilt wheels."

# ── 6. Permissions ───────────────────────────────────────────────────────────
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"
if [[ -f "$APP_DIR/.env" ]]; then
    chmod 600 "$APP_DIR/.env"
fi

# ── 7. systemd service ───────────────────────────────────────────────────────
log "Installing systemd unit..."
install -m 644 "$SCRIPT_DIR/$SERVICE_FILE" "/etc/systemd/system/$SERVICE_FILE"
systemctl daemon-reload
systemctl enable "$SERVICE_FILE" >/dev/null

# ── 8. Start / verify ────────────────────────────────────────────────────────
if [[ "$FRESH_ENV" -eq 1 ]]; then
    # .env is still an unconfigured template: enable the service but do not
    # start it — it would just crash-loop against a wrong DATABASE_URL.
    echo
    log "First-time setup complete. The service is enabled but NOT started. Next steps:"
    echo "  1. Edit the configuration:      sudo nano $APP_DIR/.env"
    echo "     Required: DATABASE_URL, DATABASE_PASSWORD, S3_BUCKET_NAME,"
    echo "     S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, PRIVATE_KEY, PUBLIC_KEY."
    echo "     (DB_DRIVER=asyncpg — the default — is correct for a VM deployment.)"
    echo "  2. Apply DB migrations if this database is not migrated yet (deploy/README.md)."
    echo "  3. Start the service:           sudo systemctl start $APP_NAME"
    echo "  4. Verify:                      curl http://127.0.0.1:$PORT/"
    exit 0
fi

log "Pre-flight check: importing the application as $SERVICE_USER ..."
if ! (cd "$APP_DIR" && runuser -u "$SERVICE_USER" -- "$APP_DIR/.venv/bin/python" -c "import app.main"); then
    die "Import failed (traceback above). Check $APP_DIR/.env — most likely a missing or invalid setting."
fi

log "Restarting service..."
systemctl restart "$SERVICE_FILE"

log "Waiting for the service to come up..."
HEALTH_OK=0
if command -v curl >/dev/null 2>&1; then
    for _ in $(seq 1 15); do
        if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
            HEALTH_OK=1
            break
        fi
        sleep 1
    done
else
    sleep 3
    if systemctl is-active --quiet "$SERVICE_FILE"; then
        HEALTH_OK=1
    fi
fi

if [[ "$HEALTH_OK" -eq 1 ]]; then
    log "Service is up: listening on port $PORT (health endpoint: GET /)."
else
    warn "The service did not pass the health check. Last log lines:"
    journalctl -u "$SERVICE_FILE" -n 30 --no-pager || true
    die "See 'journalctl -u $SERVICE_FILE -f' for live logs."
fi

log "Done. Useful commands:"
echo "  systemctl status $APP_NAME"
echo "  journalctl -u $APP_NAME -f"
echo "  systemctl restart $APP_NAME"
