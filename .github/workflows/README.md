# GitHub Actions CI/CD

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| `test.yml` | Pull request (any branch) | Run pytest against a fresh Postgres container |
| `deploy-dev.yml` | Push to `dev` branch | Build image → run migrations → deploy to dev environment |
| `deploy.yml` | Push of a `v*` tag | Build image → run migrations → deploy to production |

## How to release to production

```bash
git tag v0.3.6
git push origin v0.3.6
```

The pipeline will:
1. Build a `linux/amd64` Docker image tagged `v0.3.6`
2. Push it to Yandex Container Registry
3. Run Flyway migrations against the production database
4. Deploy a new Serverless Container revision pointing at the new image

Refresh retry recovery requires migration `V20__refresh_token_recovery.sql` before the new
application starts. The existing pipeline applies migrations before deployment. Recovery
uses the configured RSA key pair, which must be identical across instances and remain
stable during the recovery window (`REUSE_LIFETIME_MIN`, default 5 minutes).
Rotations completed before this release have no encrypted replacement and cannot recover
a previously lost response. The Android request and response formats are unchanged.

## How to deploy to dev

Push (or merge) to the `dev` branch:

```bash
git push origin dev
```

The pipeline will:
1. Build a `linux/amd64` Docker image tagged `dev-<short-sha>` (e.g. `dev-a1b2c3d`)
2. Push it to Yandex Container Registry
3. Run Flyway migrations against the dev database
4. Deploy a new Serverless Container revision for the dev container

---

## GitHub Environments

Secrets are managed via **GitHub Environments** (Settings → Environments), which allows the same secret names to hold different values per environment. Both workflows share repository-level secrets for Yandex Cloud auth.

### Environment: `prod`

Add a **Required reviewers** protection rule to prevent accidental production deploys.

**Secrets** (encrypted, masked in logs):

| Secret | Description |
|---|---|
| `FLYWAY_PASSWORD` | DB migration password |

**Variables** (plaintext, visible in logs):

| Variable | Description |
|---|---|
| `FLYWAY_URL` | JDBC URL for the production DB, e.g. `jdbc:postgresql://rc1b-xxx.mdb.yandexcloud.net:6432/lesiv_prod` |
| `FLYWAY_USER` | DB migration user |
| `CONTAINER_ID` | Yandex Serverless Container ID for production |

### Environment: `dev`

No protection rules — deploys automatically on every push to `dev`.

**Secrets** (encrypted, masked in logs):

| Secret | Description |
|---|---|
| `FLYWAY_PASSWORD` | DB migration password |

**Variables** (plaintext, visible in logs):

| Variable | Description |
|---|---|
| `FLYWAY_URL` | JDBC URL for the dev DB, e.g. `jdbc:postgresql://rc1b-xxx.mdb.yandexcloud.net:6432/lesiv_dev` |
| `FLYWAY_USER` | DB migration user (can be the same user with access to both DBs) |
| `CONTAINER_ID` | Yandex Serverless Container ID for dev (a separate container) |

### Repository-level secrets (shared by all environments)

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Description | How to get it |
|---|---|---|
| `YC_SA_JSON_KEY` | Service account JSON key (full file contents) | Yandex Cloud Console → IAM → Service Accounts → your SA → Create new key → JSON |

### Repository-level variables (shared by all environments)

| Variable | Description | How to get it |
|---|---|---|
| `YC_SA_ID` | Service account ID (e.g. `aje...`) | Yandex Cloud Console → IAM → Service Accounts → ID field |
| `YC_FOLDER_ID` | Yandex Cloud folder ID | Cloud Console → top breadcrumb, or `yc config list` |

---

## Service account permissions

The service account used (`YC_SA_JSON_KEY`) needs the following roles in your Yandex Cloud folder:

| Role | Purpose |
|---|---|
| `container-registry.images.pusher` | Push images to Container Registry |
| `serverless.containers.admin` | Deploy new container revisions (both dev and prod) |

## Fixed values (already in the workflows)

| Variable | Value |
|---|---|
| Registry | `cr.yandex/crpd2b5gg7tt3399i6c9` |
| Image name | `t-app-backend` |
| Prod image tag format | `v<semver>` (e.g. `v0.3.6`) |
| Dev image tag format | `dev-<7-char-sha>` (e.g. `dev-a1b2c3d`) |
