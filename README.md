# Tarzan

Tarzan is a team management and visibility web application that aggregates
data from Jira and GitLab to give engineering managers a single pane of glass
over their team: member profiles with skills matrices, current Jira work
items with blocking/review indicators and reassignment, and open GitLab merge
requests automatically linked back to their Jira tickets.

Built with Flask 3, SQLAlchemy 2, and Jinja2. Data is cached in a local
SQLCipher-encrypted SQLite database and refreshed in the background by
APScheduler, so dashboards always serve from the cache — no synchronous
external API calls during page loads.

The full specification lives in `.kiro/specs/team-dashboard/`
(requirements.md, design.md, tasks.md).

## Features

- **Team profiles** — name, username, avatar (JPEG/PNG/GIF/WebP up to 5 MB),
  Jira/GitLab identity mapping.
- **Skills matrix** — shared skill catalogue; per-member current proficiency
  and aspiration levels (Beginner/Intermediate/Advanced/Expert); team-wide
  skills dashboard with per-level counts and growth aspirations; bulk CSV
  import (`username,skill,current_level,aspiration_level`) that applies
  atomically, reports per-row errors, and can optionally create missing
  catalogue skills.
- **Work items dashboard** — cached Jira issues with blocked and in-review
  indicators, assignee filtering, full detail view (description, comments,
  labels, linked issues), and in-app reassignment.
- **Merge requests dashboard** — cached open GitLab MRs with review status,
  overdue-for-review highlighting (configurable 1–30 day threshold), and
  automatic Jira ticket links extracted from titles, descriptions, and branch
  names.
- **Background refresh** — configurable 1–60 minute interval (default 15);
  failures never clobber the cache; staleness warnings after 3 consecutive
  failures; last-refresh timestamps on every dashboard.
- **Security** — SQLCipher (AES-256) encryption at rest, Fernet-wrapped API
  tokens, server-side session invalidation, CSRF protection, HTTPS
  enforcement, structured JSON logs with secret scrubbing.

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Required | Description |
|---|---|---|
| `TARZAN_DB_KEY` | yes | Passphrase for database encryption key derivation |
| `TARZAN_SECRET_KEY` | yes | Flask session signing key |
| `TARZAN_ADMIN_USERNAME` | yes | Team manager login username |
| `TARZAN_ADMIN_PASSWORD` | yes | Team manager login password |
| `TARZAN_DATA_DIR` | yes | Directory for the database and avatar files |
| `TARZAN_DB_PATH` | no | Database file path (default `$TARZAN_DATA_DIR/tarzan.db`) |
| `TARZAN_HTTPS_ENFORCE` | no | `true` to redirect plain HTTP outside localhost |
| `TARZAN_ALLOW_UNENCRYPTED_DB` | no | `true` permits running without SQLCipher (development only) |
| `TARZAN_DISABLE_SCHEDULER` | no | `true` disables the background updater |
| `TARZAN_LOG_LEVEL` | no | Log level (default `INFO`) |

Missing required values are reported in a structured log line and the process
exits non-zero.

Jira/GitLab URLs, API tokens, project lists, the refresh interval, and the
review threshold are configured at runtime on the **Settings** page.

## Run with Docker Compose

```sh
cp .env.example .env   # then edit the values
docker-compose up
```

The app is served on `http://localhost:8000` (health check at `/health`).

## Run on Kubernetes

Manifests are in `k8s/`: `configmap.yaml`, `deployment.yaml`, `service.yaml`,
plus `secret.example.yaml` as a template for the required secret. Build and
push the image, create the secret, then `kubectl apply -f k8s/`.

## Local development

```sh
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt   # Windows
# .venv/bin/pip install -r requirements-dev.txt     # Linux/macOS

# Required configuration (development values shown)
export TARZAN_DB_KEY=dev-key TARZAN_SECRET_KEY=dev-secret \
       TARZAN_ADMIN_USERNAME=manager TARZAN_ADMIN_PASSWORD=devpass \
       TARZAN_DATA_DIR=./data TARZAN_ALLOW_UNENCRYPTED_DB=true

alembic upgrade head
python wsgi.py          # serves on http://127.0.0.1:8000
```

`TARZAN_ALLOW_UNENCRYPTED_DB=true` is needed on platforms without SQLCipher
wheels (e.g. Windows); the Docker image installs `sqlcipher3-binary` and runs
fully encrypted.

## Tests

```sh
.venv/Scripts/python -m pytest            # full suite
.venv/Scripts/python -m pytest tests/unit tests/smoke   # fast subset
```

The suite covers unit tests, HTTP route tests, template rendering tests, and
Hypothesis property tests for the correctness properties defined in the
design document.

## Architecture

- `app/blueprints/` — route handlers (one Blueprint per feature area)
- `app/services/` — business logic and all database access (returns DTOs)
- `app/clients/` — thin Jira/GitLab API wrappers with typed errors
- `app/templates/` — Jinja2 templates extending `base.html`, shared partials
- `app/scheduler.py` — APScheduler background updater
- `app/crypto.py` — key derivation, SQLCipher engine, Fernet helpers
- `migrations/` — Alembic migrations

Adding a new dashboard page touches at most three files: a blueprint, a
service, and a template.
