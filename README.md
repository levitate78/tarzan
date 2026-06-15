# Tarzan

Tarzan aggregates your team's Jira work items and GitLab merge requests into
a single dashboard: who's working on what, what's blocked or needs review,
how long merge requests have been open, and a team skills matrix with
aspirations for growth.

## Architecture

```
┌────────────┐      ┌─────────────┐      ┌──────────────┐
│  Frontend   │ ───▶ │   Backend    │ ───▶ │  PostgreSQL  │
│ (React SPA, │ /api │  (FastAPI)   │      │ (encrypted   │
│  nginx)     │ ◀─── │  REST API    │ ◀─── │  sensitive   │
└────────────┘      └──────┬───────┘      │  columns)    │
                            │              └──────────────┘
                            │ pub/sub (manual sync)
                            ▼
                     ┌──────────────┐      ┌──────────────┐
                     │    Worker     │ ───▶ │     Redis     │
                     │ (APScheduler) │ ◀─── │ (pub/sub)     │
                     └──────┬───────┘      └──────────────┘
                            │
                ┌───────────┴────────────┐
                ▼                        ▼
           Jira REST API           GitLab REST API
```

- **Backend** (`backend/`) — FastAPI app: auth (JWT), RBAC, team/member
  dashboards, skills matrix, Jira issue + GitLab MR APIs, connector config,
  audit logging. Sensitive columns (tokens, emails, raw API payloads) are
  encrypted at rest with AES-256-GCM.
- **Worker** (`worker/`) — background poller. On a schedule (and on-demand
  via a Redis pub/sub trigger), syncs Jira issues and GitLab merge requests,
  resolves assignees, links MRs to Jira issues by key, and computes review
  age / breach flags against the configurable threshold.
- **Frontend** (`frontend/`) — React + TypeScript + MUI SPA. Uses TanStack
  Query for local caching with background refresh, so dashboards stay fresh
  without full reloads. Served by nginx, which also reverse-proxies `/api`
  to the backend (same-origin, no CORS needed in production).
- **Database** — PostgreSQL. Schema managed via Alembic migrations.

## Local development (Docker Compose)

1. Copy the environment template and fill in secrets:

   ```bash
   cd infra/compose
   cp .env.template .env
   ```

   Generate `SECRET_KEY` and `FIELD_ENCRYPTION_KEY`:

   ```bash
   python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
   ```

   Set `SECRET_KEY` to any 32+ character random string and
   `FIELD_ENCRYPTION_KEY` to a generated value above. The `ADMIN_USERNAME` /
   `ADMIN_PASSWORD` / `ADMIN_EMAIL` values are used to create the first admin
   account on first startup (see "Initial admin account" below).

2. Start everything:

   ```bash
   docker compose up --build
   ```

   - Frontend: http://localhost:3000
   - Backend API + docs: http://localhost:8000/docs
   - Health check: http://localhost:8000/health

3. Sign in at http://localhost:3000 with the `ADMIN_USERNAME` /
   `ADMIN_PASSWORD` from your `.env`.

### Running the frontend separately (hot reload)

```bash
cd frontend
cp .env.example .env.local   # only needed if the backend isn't on :8000
npm install
npm run dev
```

The Vite dev server proxies `/api` to the backend (`VITE_BACKEND_URL`,
default `http://localhost:8000`), so the app behaves the same as in
production.

### Database migrations

The backend creates tables automatically on startup
(`Base.metadata.create_all`) for convenience in development. For anything
beyond local development, use Alembic:

```bash
cd backend
alembic upgrade head
```

Migration `002_seed_skills` seeds a default skill catalogue (languages,
frameworks, cloud, databases, devops, testing, soft skills) which can be
edited afterwards from **Skill Catalogue** (admin).

### Initial admin account

On first startup, if the `users` table is empty and `ADMIN_USERNAME` /
`ADMIN_PASSWORD` / `ADMIN_EMAIL` are set in the environment, Tarzan creates
an initial admin account automatically. This is a one-time bootstrap — once
any user exists, these variables are ignored. After logging in, create
further accounts from **Team → Add member** and remove the `ADMIN_*`
variables (or rotate the password from the **Team** page).

## Connecting Jira and GitLab

As an admin, go to **Connectors** and add:

- **Jira**: base URL (e.g. `https://your-company.atlassian.net`), an API
  token (Personal Access Token / OAuth bearer token), and the Jira project
  keys to sync (e.g. `PROJ, TEAM`).
- **GitLab**: base URL (e.g. `https://gitlab.com`), a Personal Access Token
  with `read_api` scope, and the numeric GitLab project IDs to sync.

Tokens are encrypted at rest (AES-256-GCM) and never displayed again. The
worker syncs on its configured interval (`poll_interval_seconds`, default
300s), or immediately via **Sync now** (publishes a Redis pub/sub message the
worker picks up).

To link merge requests to Jira tickets, include the Jira issue key (e.g.
`PROJ-123`) in the MR title, description, or source branch name — the worker
extracts these automatically and the dashboards cross-link them.

### Mapping team members to Jira/GitLab identities

For dashboards and the "my work" views to resolve correctly, each user
profile needs:

- `jira_username` set to their Jira display name (used to resolve issue
  assignees during sync).
- `gitlab_username` set to their GitLab username (used to match MR authors,
  reviewers, and assignees).

These can be set on **My Profile**, or by an admin via **Team**.

## Roles & permissions

| Role     | Can do |
|----------|--------|
| `viewer` | View all dashboards, issues, MRs, skills matrix |
| `member` | Above, plus edit their own profile and skill levels |
| `lead`   | Above, plus reassign Jira issues and set the review threshold |
| `admin`  | Above, plus manage team members/roles, the skill catalogue, and connectors |

## Security

- **Encryption at rest**: emails, connector base URLs/tokens, and raw Jira
  payloads are encrypted with AES-256-GCM (`app/core/encryption.py`),
  derived from `FIELD_ENCRYPTION_KEY`. Rotate by re-encrypting all rows with
  a new key (out of scope for the automatic migration).
- **Transport**: terminate TLS at your ingress/reverse proxy in production;
  `ALLOWED_ORIGINS` and HSTS are enforced when `ENVIRONMENT=production`.
- **AuthN/AuthZ**: JWT bearer tokens (`/auth/login`), bcrypt password
  hashing, and role-based access control on mutating endpoints.
- **Headers**: CSP, `X-Frame-Options`, `X-Content-Type-Options`, etc. are set
  by both the backend and the frontend's nginx config.
- **Rate limiting**: per-IP rate limiting via slowapi
  (`RATE_LIMIT_PER_MINUTE`).
- **Audit logging**: admin/lead mutations (connector changes, reassignments,
  role changes, threshold updates) are recorded in `audit_logs`.

## Running tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

## Production deployment

### Docker Compose (single host)

The same `infra/compose/docker-compose.yml` works for a small single-server
deployment. Put a TLS-terminating reverse proxy (e.g. Caddy, Traefik) in
front of the `frontend` service, and set `ALLOWED_ORIGINS` /
`ENVIRONMENT=production` accordingly.

### Kubernetes

Manifests are in `infra/k8s/` (apply with `kubectl apply -k infra/k8s`):

- `postgres.yaml` — StatefulSet + PVC
- `redis.yaml` — Deployment
- `backend.yaml` — Deployment + Service + HPA
- `worker.yaml` — single-replica Deployment (it owns the sync schedule)
- `frontend.yaml` — Deployment + Service + HPA (nginx, proxies `/api`)
- `ingress.yaml` — TLS ingress for the frontend
- `configmap.yaml` / `secret.example.yaml` — configuration

Build and push the three images (`backend/Dockerfile`,
`worker/Dockerfile`, `frontend/Dockerfile`), update the `image:` fields, and
create `tarzan-secrets` from `secret.example.yaml` with real generated
values before applying.

## Repository layout

```
backend/    FastAPI app, Alembic migrations, tests
worker/     Background sync worker (Jira + GitLab)
frontend/   React + TypeScript SPA
infra/
  compose/  Docker Compose for local/single-host deployment
  k8s/      Kubernetes manifests for scaled deployment
openapi.yaml  API contract
```
