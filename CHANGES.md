# Changes in this update

This archive contains **new and modified files only** — extract it over the
existing repository (paths match the existing layout). Everything not listed
here is untouched.

## Backend — fixes required to make the app actually run

The existing code referenced several modules that didn't exist yet. These
are thin, additive shims that wire things up without changing behaviour:

- `backend/app/api/__init__.py` *(new)* — makes `app.api` a package.
- `backend/app/api/deps.py` *(new)* — re-exports `CurrentUser`, `DB`,
  `require_role`, `write_audit_log`, `get_current_user` from
  `app.api.v1.deps`, which every router imports via `app.api.deps`.
- `backend/app/core/__init__.py` *(new)* — makes `app.core` a package (needed
  for `app.core.config`, `app.core.security`, `app.core.encryption`,
  `app.core.rbac`).
- `backend/app/core/security.py` *(new)* — re-exports
  `hash_password`/`verify_password`/`create_access_token`/`decode_access_token`
  from `app.security`, which `app.auth`, `app.models.users`, and
  `app.api.v1.deps` import via `app.core.security`.
- `backend/app/connectors/__init__.py`, `backend/app/connectors/jira.py`,
  `backend/app/connectors/gitlab.py` *(new)* — re-export `JiraConnector` /
  `GitLabConnector` from `app.jira` / `app.gitlab` under the
  `app.connectors` namespace used by `app.issues`.

Without these, `app.main:app` fails to import.

## Backend — MR ↔ Jira linking (was in the OpenAPI contract, not implemented)

The spec requires merge requests to be "linkable back to tickets" and
dashboards to show the link. `openapi.yaml` already declared `linked_mrs` on
`JiraIssueResponse` and `linked_issues` on `GitLabMRResponse`, but the
Pydantic schemas and endpoints didn't populate them.

- `backend/app/models/__init__.py` — added `JiraIssue.linked_mrs` and
  `GitLabMR.linked_issues` convenience properties over the existing
  `MRIssueLink` association.
- `backend/app/schemas/__init__.py` — added `linked_mrs: list[GitLabMRSummary]`
  to `JiraIssueResponse`, and a new `JiraIssueSummary` schema plus
  `linked_issues: list[JiraIssueSummary]` on `GitLabMRResponse`.
- `backend/app/issues.py` — eager-load `mr_links.mr` so `linked_mrs` is
  populated; also closes the Jira connector client on reassignment (was
  leaking a connection).
- `backend/app/merge_requests.py` — eager-load `issue_links.issue` so
  `linked_issues` is populated.

## Backend — initial admin bootstrap

There was no way to create the first user (user creation is admin-only).

- `backend/app/config.py` — added optional `ADMIN_USERNAME` /
  `ADMIN_PASSWORD` / `ADMIN_EMAIL` / `ADMIN_FULL_NAME` settings.
- `backend/app/main.py` — on startup, if the `users` table is empty and these
  are set, creates an initial admin account (no-op afterwards).
- `infra/compose/.env.template` — documents the new variables and adds
  `ALLOWED_ORIGINS`.

## Backend — Alembic wiring + seed data

Only `versions/001_initial_schema.py` existed; Alembic had no `env.py` /
`alembic.ini`.

- `backend/alembic.ini`, `backend/alembic/env.py`,
  `backend/alembic/script.py.mako` *(new)*.
- `backend/alembic/versions/002_seed_skills.py` *(new)* — seeds the default
  skill catalogue (languages, frameworks, cloud, databases, devops, testing,
  soft skills) referenced in the feature spec ("Skills should be derived from
  a set list, which can be easily updated").

## Backend — tests

- `backend/requirements-dev.txt`, `backend/tests/` *(new)* — smoke tests that
  import `app.main:app` and exercise the new re-export modules, RBAC, and
  field encryption. Catches the import-path issues above without needing a
  database.

## Frontend — new SPA (previously didn't exist)

`frontend/` is a new React + TypeScript + MUI + TanStack Query app:

- Auth: JWT login, stored token, `/auth/me`, role-based route guards.
- **Team Dashboard** (`/`): aggregate stats, issues-by-status chart, per-member
  summary table linking to member dashboards.
- **Work Items** (`/issues`): filterable/paginated Jira issue list, linked
  MRs, reassign dialog (lead+).
- **Merge Requests** (`/merge-requests`): filterable/paginated MR list with
  review age, breach status, and linked Jira issues.
- **Skills Matrix** (`/skills`): per-category heatmap of team skill levels,
  averages, and aspiration gaps.
- **Team** (`/team`, `/team/:userId`): directory, member dashboards, admin
  user management (create/deactivate/role).
- **My Profile** (`/profile`): edit own details, GitLab/Jira usernames,
  skill levels and aspirations.
- **Skill Catalogue** (`/admin/skills`, admin) and **Connectors**
  (`/admin/connectors`, admin: Jira/GitLab connector CRUD, review threshold,
  manual sync trigger).

TanStack Query caches dashboard/list data locally and refreshes it in the
background (`staleTime`/`refetchInterval`), per the "fast-reacting, caching
... performing background updates" requirement.

## Infra

- `infra/compose/docker-compose.yml` — added a `frontend` service (nginx,
  multi-stage build, runs as non-root on :8080, proxies `/api` to `backend`)
  and fixed the `worker` service's `env_file` path (previously pointed at a
  nonexistent `../.env`).
- `frontend/Dockerfile`, `frontend/nginx.conf` *(new)*.
- `infra/k8s/` *(new)* — namespace, configmap, secret template, Postgres
  StatefulSet, Redis, backend/worker/frontend Deployments (with HPAs for
  backend/frontend), and an Ingress.
- `README.md` *(new)* — setup, env vars, connector setup, roles, security
  notes, and deployment instructions for both Compose and Kubernetes.
- `.gitignore` *(new)*.
