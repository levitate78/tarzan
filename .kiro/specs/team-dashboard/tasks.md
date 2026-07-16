# Implementation Plan: Team Dashboard (Tarzan)

## Overview

Implement Tarzan as a Flask 3.x server-rendered web application with SQLCipher-encrypted SQLite storage, APScheduler background refresh, Jira and GitLab API integration, and Blueprint-based routing. The implementation follows the service-layer architecture defined in the design, building from infrastructure and data models up through services, routes, and templates, finishing with the scheduler and deployment artefacts.

## Tasks

- [ ] 1. Project scaffold and configuration layer
  - Create the directory structure: `app/`, `app/blueprints/`, `app/services/`, `app/clients/`, `app/templates/`, `app/templates/partials/`, `tests/unit/`, `tests/property/`, `tests/integration/`, `tests/smoke/`
  - Create `pyproject.toml` (or `requirements.txt`) pinning Flask 3.x, SQLAlchemy 2.x, pysqlcipher3, alembic, APScheduler 3.x, python-gitlab, jira, Flask-Login, itsdangerous, python-json-logger, hypothesis, pytest, pytest-flask
  - Create `app/config.py` with a `Config` dataclass that reads and validates all required environment variables (`TARZAN_DB_KEY`, `TARZAN_DATA_DIR`, `TARZAN_HTTPS_ENFORCE`, etc.) and exits with a non-zero code plus a descriptive log line if any required variable is absent
  - Create `app/logging_setup.py` that configures `python-json-logger` to emit structured JSON on stdout with fields: `timestamp` (ISO 8601), `severity`, `message`; register a log filter that scrubs known secret patterns
  - _Requirements: 12.3, 12.4, 12.5_


- [ ] 2. Encryption and database initialisation
  - [ ] 2.1 Implement `app/crypto.py` with PBKDF2-HMAC-SHA256 key derivation from `TARZAN_DB_KEY`, SQLCipher `PRAGMA key` connection event, and Fernet field-level encryption/decryption helpers
    - Derive the database key deterministically so it is reproducible across restarts without being stored
    - Expose `get_fernet()` that returns a `Fernet` instance using a key stored encrypted in the `CREDENTIAL` table (bootstrap on first run)
    - _Requirements: 10.1, 10.6_
  - [ ]* 2.2 Write property test for credential encryption round-trip
    - **Property 30: Credential encryption round-trip**
    - **Validates: Requirements 10.1, 10.6**
    - Use `st.text()` for plaintext values; assert stored bytes differ from `value.encode()`; assert round-trip returns original value; assert raw `.db` file bytes do not contain plaintext
  - [ ] 2.3 Implement SQLAlchemy `DeclarativeBase` models in `app/models.py` for all tables: `TeamMember`, `Skill`, `SkillsMatrix`, `WorkItem`, `MergeRequest`, `TicketLink`, `JiraProject`, `GitLabProject`, `Credential`, `RefreshLog`, `Config`
    - Define all columns, constraints, and relationships per the ER diagram in the design
    - Include `__table_args__` unique constraints where required (username, skill name, issue_key, gitlab_id, credential key)
    - _Requirements: 1.2, 2.1, 4.1, 6.1, 10.1_
  - [ ] 2.4 Create the Alembic migration environment (`alembic.ini`, `migrations/env.py`) and generate the initial migration that creates all tables
    - Migration must use the SQLCipher-aware engine from `app/crypto.py`
    - _Requirements: 12.1_


- [ ] 3. Application factory and core infrastructure
  - [ ] 3.1 Implement `app/__init__.py` `create_app(config)` factory: initialise Flask, bind SQLAlchemy with the SQLCipher engine, register Flask-Login, configure itsdangerous signed cookies, register a `before_request` hook for HTTPS enforcement and session validity, register error handlers for 401/403/404/500
    - HTTPS enforcement must redirect plain HTTP to HTTPS (301/302) and must not process the request body before redirecting when `TARZAN_HTTPS_ENFORCE=true`
    - _Requirements: 10.4, 10.5, 10.7, 11.2_
  - [ ]* 3.2 Write property test for HTTPS enforcement
    - **Property 34: HTTPS enforcement in non-localhost context**
    - **Validates: Requirements 10.7**
    - Use `st.from_regex(r"http://[^/]+/.*")` to generate plain HTTP URLs; assert response is 301/302; assert no request body is processed before redirect
  - [ ]* 3.3 Write property test for session invalidation after logout
    - **Property 33: Session invalidation after logout**
    - **Validates: Requirements 10.5**
    - Use `st.uuids()` to generate session tokens; after logout, assert subsequent authenticated request returns HTTP 401


- [ ] 4. Base template and shared partials
  - [ ] 4.1 Create `app/templates/base.html` with full-page skeleton using semantic HTML elements (`header`, `nav`, `main`, `footer`); include blocks for `title`, `content`, and `extra_scripts`; link to a project CSS file
    - All `<img>` elements must include `alt` attributes
    - Ensure all interactive elements are keyboard-reachable with visible focus indicator
    - _Requirements: 11.1, 11.4, 11.5, 11.6_
  - [ ] 4.2 Create shared partials: `_nav.html` (navigation bar), `_flash_messages.html` (alert/error display), `_staleness_warning.html` (data staleness banner showing `source_id` and last successful refresh timestamp)
    - `_staleness_warning.html` must be conditionally included based on `CacheService.consecutive_failure_count() >= 3`
    - _Requirements: 8.5, 8.6, 11.1_
  - [ ]* 4.3 Write property test for alt text length invariant
    - **Property 35: Alt text length invariant**
    - **Validates: Requirements 11.6**
    - Render all template pages; assert every `<img>` has a non-empty `alt` attribute with length ≤ 125 characters
  - [ ]* 4.4 Write property test for HTML output escaping
    - **Property 32: HTML output escapes special characters**
    - **Validates: Requirements 10.3**
    - Use `st.text(alphabet=st.characters(whitelist_categories=("P",)))` containing `<`, `>`, `&`, `"`, `'`; assert rendered output contains HTML entity escapes and not raw unescaped characters


- [ ] 5. Authentication blueprint and credential service
  - [ ] 5.1 Implement `app/services/credential_service.py` `CredentialService` with `get_credential(key)` (decrypts on read via Fernet) and `set_credential(key, value)` (encrypts on write); never log or expose plaintext values; raise `StorageError` if the credential store is unavailable
    - _Requirements: 10.1, 10.2, 10.8_
  - [ ] 5.2 Implement `app/blueprints/auth.py` (`auth_bp`) with `/auth/login` (GET/POST) and `/auth/logout` routes; use Flask-Login `login_user` / `logout_user`; invalidate session server-side on logout; redirect unauthenticated requests to login
    - _Requirements: 10.4, 10.5_
  - [ ] 5.3 Create `app/templates/auth/login.html` extending `base.html` with a login form; include CSRF token via itsdangerous
    - _Requirements: 11.1_
  - [ ]* 5.4 Write property test for no secrets in log output
    - **Property 31: No secrets in log output**
    - **Validates: Requirements 10.2**
    - Use `st.text()` as secret value; perform credential read/write, API fetch, and profile CRUD operations; capture log output; assert secret value does not appear as a substring in any log line


- [ ] 6. Profile service and blueprint
  - [ ] 6.1 Implement `app/services/profile_service.py` `ProfileService` with `list_profiles()`, `get_profile(username)`, `create_profile(data)`, `update_profile(username, data)`, `save_avatar(username, file_bytes, mime_type)`
    - Validate: required fields non-empty/non-whitespace-only, username uniqueness (case-insensitive), avatar MIME type in `{image/jpeg, image/png, image/gif, image/webp}`, avatar size ≤ 5 242 880 bytes
    - `save_avatar` must store files at `TARZAN_DATA_DIR/avatars/<username>.<ext>` and validate the path is within the designated directory
    - Raise `ValidationError`, `ConflictError`, or `NotFoundError` as appropriate; never return ORM model objects — return `ProfileDTO` dataclasses
    - _Requirements: 1.2, 1.3, 1.4, 1.6, 1.7_
  - [ ]* 6.2 Write property test for profile persistence round-trip
    - **Property 1: Profile persistence round-trip**
    - **Validates: Requirements 1.2, 1.3**
    - Use `st.text()` for name/username; assert create then get returns matching name, username, avatar path; assert update then get returns updated values
  - [ ]* 6.3 Write property test for whitespace-only profile fields rejected
    - **Property 2: Whitespace-only profile fields are rejected**
    - **Validates: Requirements 1.4**
    - Use `st.text(alphabet=string.whitespace)` for name/username; assert `ValidationError` is raised and database state is unchanged
  - [ ]* 6.4 Write property test for username uniqueness invariant
    - **Property 3: Username uniqueness invariant**
    - **Validates: Requirements 1.6**
    - Use `st.text()` sampled twice; assert duplicate username (any case/whitespace variant) is rejected
  - [ ]* 6.5 Write property test for avatar file validation
    - **Property 4: Avatar file validation**
    - **Validates: Requirements 1.7**
    - Use `st.binary()` + `st.sampled_from(MIME_TYPES)`; assert accepts iff MIME in allowed set AND size ≤ 5 MiB; assert rejection leaves avatar store unchanged


  - [ ] 6.6 Implement `app/blueprints/profiles.py` (`profiles_bp`) with routes: `GET /profiles/` (list), `GET /profiles/<username>` (detail), `GET/POST /profiles/new` (create), `GET/POST /profiles/<username>/edit` (edit), `POST /profiles/<username>/avatar` (avatar upload)
    - Validate path/query parameters; catch `ValidationError`/`ConflictError` and set flash messages; require authentication via `@login_required`
    - Avatar serving route must validate path is within `TARZAN_DATA_DIR/avatars/` before streaming
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_
  - [ ] 6.7 Create profile templates: `app/templates/profiles/index.html`, `detail.html`, `edit.html` — all extending `base.html`; reuse `_flash_messages.html` partial; include all required profile fields in rendered output
    - _Requirements: 1.1, 11.1, 11.4, 11.5_

- [ ] 7. Checkpoint — core profile feature
  - Ensure all profile service unit tests and property tests pass, ask the user if questions arise.


- [ ] 8. Skills service and blueprint
  - [ ] 8.1 Implement `app/services/skills_service.py` `SkillsService` with `list_catalogue()`, `add_skill(name)`, `remove_skill(skill_id)`, `assign_skill(username, skill_id, current, aspiration)`, `get_team_skills_summary()`
    - Validate proficiency level against `{"Beginner", "Intermediate", "Advanced", "Expert"}` enum
    - `add_skill` must enforce case-insensitive uniqueness; `remove_skill` must deprecate rather than delete if Skills_Matrix references exist (return `RemovalResult` with reference count)
    - `get_team_skills_summary` must include all skills from catalogue, zero counts included, and aspiration counts where aspiration > current in the level ordering
    - Return `SkillDTO`, `SkillSummaryDTO` dataclasses; never return ORM objects
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4_
  - [ ]* 8.2 Write property test for skill assignment round-trip
    - **Property 5: Skill assignment round-trip**
    - **Validates: Requirements 2.2, 2.3**
    - Use `st.sampled_from(LEVELS)` for current and aspiration levels; assert assigned values match retrieved Skills_Matrix entry
  - [ ]* 8.3 Write property test for invalid proficiency level rejected
    - **Property 6: Invalid proficiency level is rejected**
    - **Validates: Requirements 2.5**
    - Use `st.text().filter(lambda x: x not in LEVELS)`; assert `ValidationError` raised and existing entry unchanged
  - [ ]* 8.4 Write property test for deprecated skill references preserved
    - **Property 7: Deprecated skill references are preserved**
    - **Validates: Requirements 2.4**
    - Use `st.integers(min_value=1, max_value=20)` for reference count; assert all Skills_Matrix entries intact after `remove_skill()` and `skill_deprecated` flag is True
  - [ ]* 8.5 Write property test for skill name case-insensitive uniqueness
    - **Property 8: Skill name case-insensitive uniqueness**
    - **Validates: Requirements 2.7**
    - Use `st.text()` + `str.upper()/lower()` permutations; assert duplicate case variants are rejected
  - [ ]* 8.6 Write property test for skills summary aggregation correctness
    - **Property 9: Skills summary aggregation correctness**
    - **Validates: Requirements 3.1, 3.2, 3.3**
    - Use `st.lists(st.builds(MatrixEntry))`; assert every skill appears in result, counts at each level match matrix, zero counts included, aspiration counts correct
  - [ ]* 8.7 Write property test for skills summary reflects latest state
    - **Property 10: Skills summary reflects latest matrix state**
    - **Validates: Requirements 3.4**
    - Same strategy as Property 9 plus an update step; assert summary reflects updated counts within same transaction context


  - [ ] 8.8 Implement `app/blueprints/skills.py` (`skills_bp`) with routes: `GET /skills/catalogue` (catalogue management), `POST /skills/catalogue` (add skill), `DELETE /skills/catalogue/<skill_id>` (remove with confirmation), `GET /skills/dashboard` (team skills summary), `GET/POST /skills/matrix/<username>` (assign/edit skills for a member)
    - Enforce `@login_required` on all mutation routes; catch service exceptions and render appropriate flash messages
    - Removal confirmation prompt must display the Skills_Matrix reference count returned by `remove_skill()`
    - _Requirements: 2.1, 2.2, 2.6, 2.7, 2.8, 3.1, 3.5_
  - [ ] 8.9 Create skills templates: `app/templates/skills/catalogue.html` and `dashboard.html` extending `base.html`; reuse `_skill_badge.html` partial for proficiency display; include all required dashboard fields and zero counts
    - _Requirements: 3.1, 3.2, 3.3, 11.1_

- [ ] 9. Checkpoint — skills feature
  - Ensure all skills service unit tests and property tests pass, ask the user if questions arise.


- [ ] 10. API clients
  - [ ] 10.1 Implement `app/clients/jira_client.py` `JiraClient` wrapping the `jira` PyPI library: `__init__(server, token, timeout_seconds=10)`, `search_issues(jql)`, `get_issue(issue_key)`, `update_assignee(issue_key, account_id)`
    - Handle pagination in `search_issues`; enforce timeout on all calls; raise `JiraClientError` (typed, with source info) on network timeout, HTTP 4xx/5xx — never leak library-specific exceptions to callers
    - _Requirements: 4.1, 5.1, 5.4_
  - [ ] 10.2 Implement `app/clients/gitlab_client.py` `GitLabClient` wrapping `python-gitlab`: `__init__(url, token, timeout_seconds=10)`, `list_merge_requests(project_id, state="opened")`
    - Handle pagination; enforce timeout; raise `GitLabClientError` on failures
    - _Requirements: 6.1_


- [ ] 11. Cache service
  - [ ] 11.1 Implement `app/services/cache_service.py` `CacheService` with `get_last_refresh(source_id)`, `record_refresh(source_id, success, error=None)`, `consecutive_failure_count(source_id)`
    - `consecutive_failure_count` queries `REFRESH_LOG` rows for `source_id` ordered by `attempted_at DESC` until a success row is found or all rows are exhausted
    - Prune `REFRESH_LOG` rows older than 30 days on startup
    - _Requirements: 8.5, 8.6_
  - [ ]* 11.2 Write property test for consecutive failure count triggers staleness warning
    - **Property 26: Consecutive failure count triggers staleness warning**
    - **Validates: Requirements 8.5**
    - Use `st.integers(min_value=0)` for failure count; assert `consecutive_failure_count() >= 3` when N ≥ 3 consecutive failures; assert count resets to 0 after a success row; assert dashboard render includes staleness warning iff count ≥ 3
  - [ ]* 11.3 Write property test for last refresh timestamp round-trip
    - **Property 27: Last refresh timestamp round-trip**
    - **Validates: Requirements 8.6**
    - Use `st.datetimes()` for recorded time; assert `get_last_refresh()` returns datetime within 1 second; assert rendered dashboard shows timestamp accurate to nearest minute
  - [ ]* 11.4 Write property test for cache persistence across restart simulation
    - **Property 28: Cache persistence across restart simulation**
    - **Validates: Requirements 9.1**
    - Use `st.lists(st.builds(WorkItemDTO))`; write via service methods; close and reopen SQLCipher connection; assert all records readable with all fields intact
  - [ ]* 11.5 Write property test for review threshold and interval validation
    - **Property 22: Review threshold validation**
    - **Validates: Requirements 6.6, 8.1**
    - Use `st.integers()` for threshold/interval values; assert values in [1,30] (threshold) and [1,60] (interval) are accepted; assert values outside range raise `ValidationError`


- [ ] 12. Jira service and work items blueprint
  - [ ] 12.1 Implement `app/services/jira_service.py` `JiraService` with `list_work_items(assignee=None)`, `get_work_item(issue_key)`, `reassign_work_item(issue_key, assignee_account_id)`, `fetch_and_cache(project_key)`
    - `list_work_items` reads only from the cache; never calls `JiraClient` synchronously during a page request
    - `fetch_and_cache` writes all returned items to the database, records the refresh via `CacheService`, and leaves existing items untouched on any `JiraClientError`
    - `reassign_work_item` must call the Jira API within 5 seconds; on success update the cached item; on error or timeout leave cache unchanged and raise `ReassignError` / `TimeoutError`
    - Filter `list_work_items` by `assignee_account_id` or `assignee_display_name` when `assignee` is provided
    - Return `WorkItemDTO` / `WorkItemDetailDTO` dataclasses
    - _Requirements: 4.1, 4.2, 4.6, 5.1, 5.2, 5.3, 5.4, 9.5_
  - [ ]* 12.2 Write property test for Jira fetch-and-cache round-trip
    - **Property 11: Fetch-and-cache round-trip (Jira)**
    - **Validates: Requirements 4.1, 8.3**
    - Use `st.lists(st.builds(WorkItemDTO))` with mocked `JiraClient`; assert each item retrievable via `list_work_items()` with all fields intact after `fetch_and_cache()`
  - [ ]* 12.3 Write property test for Jira cache retention on failure
    - **Property 12: Cache retention on fetch failure (Jira)**
    - **Validates: Requirements 4.2, 8.4, 9.3**
    - Use `st.lists(...)` + mocked `JiraClientError`; assert cache contents unchanged after failed `fetch_and_cache()`
  - [ ]* 12.4 Write property test for assignee filter correctness
    - **Property 15: Assignee filter returns only matching items**
    - **Validates: Requirements 4.6**
    - Use `st.lists(st.builds(WorkItemDTO))` + `st.text()` filter value; assert every returned item matches filter and no matching item is omitted
  - [ ]* 12.5 Write property test for cache update after successful reassignment
    - **Property 17: Cache update after successful reassignment**
    - **Validates: Requirements 5.2**
    - Use `st.builds(WorkItemDTO)` + `st.text()` new assignee with mocked success; assert `get_work_item()` returns updated `assignee_account_id`; assert no other fields modified
  - [ ]* 12.6 Write property test for cache unchanged after failed reassignment
    - **Property 18: Cache unchanged after failed or timed-out reassignment**
    - **Validates: Requirements 5.3, 5.4**
    - Same setup with mocked error/timeout; assert all fields unchanged after failed `reassign_work_item()`
  - [ ]* 12.7 Write property test for no synchronous API call during render (Jira)
    - **Property 29: No synchronous external API call during page render (Jira)**
    - **Validates: Requirements 9.5**
    - For non-empty cache, call `list_work_items()` and `get_work_item()`; assert mock `JiraClient` records zero calls


  - [ ] 12.8 Implement `app/blueprints/jira.py` (`jira_bp`) with routes: `GET /jira/` (work items dashboard, filterable by assignee), `GET /jira/<issue_key>` (detail view), `POST /jira/<issue_key>/reassign` (reassignment)
    - Enforce `@login_required`; catch `ReassignError` and `TimeoutError` and render descriptive flash messages; present only configured team members as reassignment candidates
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 5.1, 5.3, 5.4, 5.5, 5.6_
  - [ ] 12.9 Create `app/templates/partials/_work_item_card.html` partial and Jira templates: `jira/index.html`, `jira/detail.html` extending `base.html`
    - Work item card must render: issue key, summary, assignee, status, priority; blocked indicator (badge/icon) for blocked status; in-review indicator (visually distinct) for in-review status; include `_staleness_warning.html`
    - _Requirements: 4.3, 4.4, 4.5, 8.5, 8.6_

- [ ] 13. GitLab service and merge requests blueprint
  - [ ] 13.1 Implement `app/services/gitlab_service.py` `GitLabService` with `list_merge_requests(author_or_reviewer=None)`, `fetch_and_cache(project_id)`
    - `list_merge_requests` reads only from cache; never calls `GitLabClient` synchronously
    - `fetch_and_cache` leaves existing items untouched on `GitLabClientError`; records refresh via `CacheService`
    - Return `MergeRequestDTO` dataclasses
    - _Requirements: 6.1, 6.2, 6.5, 9.5_
  - [ ]* 13.2 Write property test for GitLab fetch-and-cache round-trip
    - **Property 11: Fetch-and-cache round-trip (GitLab)**
    - **Validates: Requirements 6.1, 8.3**
    - Use `st.lists(st.builds(MergeRequestDTO))` with mocked `GitLabClient`; assert each item retrievable with all fields intact after `fetch_and_cache()`
  - [ ]* 13.3 Write property test for GitLab cache retention on failure
    - **Property 12: Cache retention on fetch failure (GitLab)**
    - **Validates: Requirements 6.2, 8.4, 9.3**
    - Use `st.lists(...)` + mocked `GitLabClientError`; assert cache contents unchanged
  - [ ]* 13.4 Write property test for MR author/reviewer filter correctness
    - **Property 15: Assignee filter returns only matching items (GitLab)**
    - **Validates: Requirements 6.5**
    - Use `st.lists(st.builds(MergeRequestDTO))` + `st.text()` filter; assert every returned MR matches filter and no matching MR is omitted
  - [ ]* 13.5 Write property test for no synchronous API call during render (GitLab)
    - **Property 29: No synchronous external API call during page render (GitLab)**
    - **Validates: Requirements 9.5**
    - Call `list_merge_requests()` with non-empty cache; assert mock `GitLabClient` records zero calls


  - [ ] 13.6 Implement `app/blueprints/gitlab.py` (`gitlab_bp`) with route: `GET /gitlab/` (merge requests dashboard, filterable by team member); enforce `@login_required`
    - _Requirements: 6.3, 6.4, 6.5_
  - [ ] 13.7 Create `app/templates/partials/_mr_card.html` partial and `app/templates/gitlab/index.html` extending `base.html`
    - MR card must render: title, author, target branch, creation date, review status (Awaiting Review / Changes Requested / Approved); review threshold badge/coloured border when age exceeds configured threshold; include `_staleness_warning.html`
    - _Requirements: 6.3, 6.4, 8.5, 8.6_

- [ ] 14. Ticket linking
  - [ ] 14.1 Implement `app/ticket_linking.py` `extract_ticket_references(text)` that returns a set of unique Jira issue key substrings matching `[A-Z]+-[0-9]{1,6}` where the uppercase prefix matches a configured Jira project key; empty input or no matches must return an empty set without error
    - Wire into `GitLabService.fetch_and_cache()`: extract references from each MR title, description, and source branch; persist as `TicketLink` rows
    - _Requirements: 7.1, 7.3, 7.4_
  - [ ]* 14.2 Write property test for ticket reference extraction correctness
    - **Property 23: Ticket reference extraction correctness**
    - **Validates: Requirements 7.1, 7.4**
    - Use `st.text()` including valid/invalid patterns; assert returned set contains exactly the substrings matching the pattern for configured project keys; assert no match returns empty set without error
  - [ ]* 14.3 Write property test for ticket reference deduplication
    - **Property 24: Ticket reference deduplication**
    - **Validates: Requirements 7.3**
    - Use `st.text()` with repeated valid references; assert result is a set with each reference appearing exactly once


- [ ] 15. Rendering / template property tests
  - [ ] 15.1 Write unit tests in `tests/unit/test_renderers.py` covering work item and MR card rendering for all required fields
    - _Requirements: 4.3, 6.3_
  - [ ]* 15.2 Write property test for work item rendering contains required fields
    - **Property 13: Work item rendering contains required fields**
    - **Validates: Requirements 4.3**
    - Use `st.builds(WorkItemDTO)` with non-null required fields; assert rendered HTML contains issue key, summary, assignee, status, and priority as visible text
  - [ ]* 15.3 Write property test for blocked and in-review indicators are distinct
    - **Property 14: Blocked and In-Review indicators are distinct and correct**
    - **Validates: Requirements 4.4, 4.5**
    - Use `st.sampled_from(["Blocked", "In Review", "Open"])`; assert blocked indicator present and in-review absent for blocked; vice versa for in-review; neither present for open
  - [ ]* 15.4 Write property test for work item detail rendering
    - **Property 16: Work item detail rendering contains all detail fields**
    - **Validates: Requirements 4.7**
    - Use `st.builds(WorkItemDetailDTO)` with non-null description, comments, labels, linked issues; assert all four sections present in rendered HTML
  - [ ]* 15.5 Write property test for reassignment candidate list
    - **Property 19: Reassignment candidate list is a subset of configured team members**
    - **Validates: Requirements 5.6**
    - Use `st.lists(st.builds(TeamMember))`; assert rendered reassignment UI contains exactly the configured team members and no others
  - [ ]* 15.6 Write property test for MR rendering contains required fields
    - **Property 20: Merge request rendering contains required fields**
    - **Validates: Requirements 6.3**
    - Use `st.builds(MergeRequestDTO)` with non-null required fields; assert title, author, target_branch, created_at, review_status all present; assert review_status is one of the three valid values
  - [ ]* 15.7 Write property test for review threshold indicator
    - **Property 21: Review threshold indicator appears iff age exceeds threshold**
    - **Validates: Requirements 6.4**
    - Use `st.integers(1, 30)` for threshold + `st.timedeltas()` for MR age; assert indicator present iff `age.days > threshold`; assert absent when age ≤ threshold
  - [ ]* 15.8 Write property test for ticket link rendering
    - **Property 25: Ticket link rendering**
    - **Validates: Requirements 7.2, 7.3**
    - Use `st.lists(st.from_regex(r"[A-Z]+-\d{1,6}"))` for resolved references; assert one `<a>` element per distinct reference pointing to the configured Jira instance URL

- [ ] 16. Checkpoint — Jira, GitLab, and ticket linking
  - Ensure all Jira service, GitLab service, ticket linking, and renderer property tests pass, ask the user if questions arise.


- [ ] 17. Settings blueprint
  - [ ] 17.1 Implement `app/blueprints/settings.py` (`settings_bp`) with routes: `GET /settings/` (view current configuration), `POST /settings/credentials` (set API tokens via `CredentialService`), `POST /settings/refresh-interval` (validate [1,60] and persist to `CONFIG` table), `POST /settings/review-threshold` (validate [1,30] and persist), `POST /settings/projects` (add/remove Jira and GitLab project configurations)
    - Enforce `@login_required`; validate all inputs; never echo invalid values in error responses
    - _Requirements: 6.6, 8.1, 10.3, 12.3_
  - [ ] 17.2 Create `app/templates/settings/index.html` extending `base.html` with forms for all settings; include `_flash_messages.html`
    - _Requirements: 11.1_

- [ ] 18. Background scheduler
  - [ ] 18.1 Implement `app/scheduler.py` with `start_scheduler(app)` and `refresh_all(app)`: create a `BackgroundScheduler`, read interval from `CONFIG` table (default 15 minutes), schedule `refresh_all` at that interval within the Flask app context; catch all exceptions in `refresh_all` and record via `CacheService.record_refresh()` — never crash the scheduler thread
    - `refresh_all` must call `JiraService.fetch_and_cache()` for every enabled `JiraProject` and `GitLabService.fetch_and_cache()` for every enabled `GitLabProject`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_
  - [ ] 18.2 Wire `start_scheduler(app)` into the `create_app` factory so the scheduler starts automatically when the app initialises
    - _Requirements: 8.1_


- [ ] 19. Deployment artefacts
  - [ ] 19.1 Create `Dockerfile` using a Python base image; install dependencies from `pyproject.toml`; run `alembic upgrade head` as the entrypoint pre-command; start the app with Gunicorn; define a `HEALTHCHECK` on `/health`
    - _Requirements: 12.1, 12.3_
  - [ ] 19.2 Create `docker-compose.yml` with the Tarzan service, volume mounts for `TARZAN_DATA_DIR` and the database file, environment variable references (no hardcoded values), and a `healthcheck` configuration; all services must be healthy within 120 seconds
    - _Requirements: 12.1, 12.3_
  - [ ] 19.3 Create Kubernetes manifests in `k8s/`: `deployment.yaml`, `service.yaml`, `configmap.yaml`; externalise all environment-specific configuration via `ConfigMap` and `Secret` references; no hardcoded values in image
    - _Requirements: 12.2, 12.3_
  - [ ] 19.4 Implement `app/blueprints/health.py` with `GET /health` route that returns `{"status": "ok"}` with HTTP 200 when the app is running and the database connection is healthy
    - _Requirements: 12.1_

- [ ] 20. Smoke and integration test wiring
  - [ ] 20.1 Write `tests/smoke/test_startup.py` verifying: all required env vars present → app starts and `GET /health` returns 200; missing required env var → app exits with non-zero code and logs the missing variable name
    - _Requirements: 12.4, 12.5_
  - [ ]* 20.2 Write integration tests in `tests/integration/test_jira_client.py` using VCR cassettes: `search_issues` with pagination, `update_assignee` success and 4xx error paths
    - _Requirements: 4.1, 5.1_
  - [ ]* 20.3 Write integration tests in `tests/integration/test_gitlab_client.py` using VCR cassettes: `list_merge_requests` with pagination
    - _Requirements: 6.1_
  - [ ]* 20.4 Write integration test in `tests/integration/test_scheduler.py` using VCR cassettes: `refresh_all()` end-to-end; assert cache populated and `RefreshLog` records written
    - _Requirements: 8.1, 8.3_
  - [ ]* 20.5 Write integration test verifying raw SQLCipher `.db` file bytes do not contain any plaintext record written via service methods
    - _Requirements: 10.1, 10.6_

- [ ] 21. Final checkpoint — full test suite
  - Ensure all unit tests, property tests, smoke tests, and integration tests pass; run linting; verify no obvious regressions, ask the user if questions arise.


- [x] 22. Bulk skills CSV import
  - [x] 22.1 Implement `SkillsService.import_matrix_csv(csv_text, create_missing_skills=False)` returning `SkillsImportResult`
    - Parse a header row (`username`, `skill`, `current_level`, optional `aspiration_level`; case/order insensitive); validate every row (existing username case-insensitive, skill in catalogue unless `create_missing_skills`, levels case-insensitive against the defined set, no duplicate username–skill pairs); apply atomically in a single commit or import nothing and return per-row errors that never echo the invalid value
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_
  - [x] 22.2 Implement `GET/POST /skills/import` in `skills_bp` and `app/templates/skills/import.html`
    - Enforce `@login_required` and CSRF; reject uploads over 1 MB or not valid UTF-8; render the format description, the create-missing-skills option, per-row errors, and a success summary; link the page from the skills dashboard and catalogue
    - _Requirements: 13.1, 13.2, 13.8, 13.9_
  - [x]* 22.3 Write property tests for bulk import
    - **Property 36: Bulk import round-trip**, **Property 37: Bulk import atomicity**, **Property 38: Missing-skill creation is gated by the option**
    - **Validates: Requirements 13.2, 13.3, 13.4, 13.5, 13.6, 13.7**
  - [x] 22.4 Write unit tests covering header handling, row validation errors, update-vs-create semantics, and the upload routes (auth, CSRF, size/encoding rejection)
    - _Requirements: 13.1, 13.3, 13.8, 13.9_


- [x] 23. Manual data refresh
  - [x] 23.1 Add shared request-scoped client builders (`build_jira_client`, `build_gitlab_client`) to `app/blueprints/common.py` and reuse them for reassignment and manual refresh
    - _Requirements: 14.2_
  - [x] 23.2 Implement `POST /jira/refresh` and `POST /gitlab/refresh`: for every enabled project call the same `fetch_and_cache()` path the scheduler uses, flash a summary with item counts and any failed projects, and redirect to the dashboard; when the URL/token is unconfigured flash an error pointing at Settings without recording refresh failures
    - Add a "Refresh now" button (POST form with CSRF) to the work items and merge requests dashboards
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_
  - [x] 23.3 Write unit tests: authentication required, unconfigured source flashes a Settings pointer, successful refresh caches items and reports counts, failed project retains cache and is named in the flash
    - _Requirements: 14.1, 14.3, 14.4, 14.5_


- [x] 24. Change password
  - [x] 24.1 Add `get_admin_password_hash()` / `set_admin_password()` to `ConfigService` (hash stored in the CONFIG table inside the encrypted database) and make login prefer the stored hash over the environment-derived hash
    - _Requirements: 15.2, 15.3_
  - [x] 24.2 Implement `GET/POST /auth/change-password` and `app/templates/auth/change_password.html`: require current password, new password (≥ 8 chars), and confirmation; on success store the new hash, delete all other USER_SESSION rows, and flash a confirmation; on failure flash a descriptive error without echoing any submitted value; link the page from the Settings page
    - _Requirements: 15.1, 15.2, 15.4, 15.5, 15.6_
  - [x]* 24.3 Write property test for password change round-trip
    - **Property 39: Password change round-trip**
    - **Validates: Requirements 15.2, 15.3**
  - [x] 24.4 Write unit tests: old password rejected after change, new password works across restart-equivalent (fresh app on same DB), wrong current password / short password / mismatched confirmation all rejected without change, other sessions invalidated
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_


## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP; core implementation tasks must not be skipped.
- Each task references specific requirements for traceability.
- Checkpoints at tasks 7, 9, 16, and 21 ensure incremental validation at natural feature boundaries.
- Property tests (Hypothesis) validate universal correctness properties; unit tests cover specific examples and error branches.
- All 35 design correctness properties are covered: Properties 1–4 in task 6, 5–10 in task 8, 11–12 in tasks 12–13, 13–21 in task 15, 22 in task 11, 23–25 in tasks 14–15, 26–29 in tasks 11–13, 30–35 in tasks 2–4.
- Integration tests requiring VCR cassettes or live API access are marked optional; they can be deferred until API credentials are available.
- The scheduler is wired last (task 18) to avoid background refresh interfering with unit test isolation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.3"] },
    { "id": 1, "tasks": ["2.2", "2.4", "3.1"] },
    { "id": 2, "tasks": ["3.2", "3.3", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "4.4", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["6.1", "8.1", "10.1", "10.2", "11.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "6.4", "6.5", "8.2", "8.3", "8.4", "8.5", "8.6", "8.7", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 7, "tasks": ["6.6", "6.7", "8.8", "8.9", "12.1", "13.1", "14.1"] },
    { "id": 8, "tasks": ["12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "13.2", "13.3", "13.4", "13.5", "14.2", "14.3"] },
    { "id": 9, "tasks": ["12.8", "12.9", "13.6", "13.7", "15.1"] },
    { "id": 10, "tasks": ["15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8"] },
    { "id": 11, "tasks": ["17.1", "18.1"] },
    { "id": 12, "tasks": ["17.2", "18.2", "19.1", "19.4"] },
    { "id": 13, "tasks": ["19.2", "19.3"] },
    { "id": 14, "tasks": ["20.1", "20.2", "20.3", "20.4", "20.5"] }
  ]
}
```
