# Requirements Document

## Introduction

Tarzan is a team management and visibility web application that aggregates data from Jira and GitLab to give engineering managers and team leads a single pane of glass over their team. The application surfaces team member profiles with skills matrices, current Jira work items with assignment and blocking status, and open GitLab merge requests linked back to tickets. It is designed to be deployed locally via Docker Compose or Kubernetes, with a security-first approach, local data caching, and background refresh of external API data.

## Glossary

- **Application**: The Tarzan web application described in this document.
- **Team_Manager**: A user with administrative access who can configure teams, skill sets, and thresholds.
- **Team_Member**: A user whose profile, work items, and merge requests are tracked by the Application.
- **Profile**: A record capturing a Team_Member's name, username, avatar photo, and Skills_Matrix.
- **Skills_Matrix**: A structured record of skills associated with a Team_Member, drawn from the Skill_Catalogue, each annotated with a current proficiency level and an optional aspiration level.
- **Skill_Catalogue**: The administrator-maintained list of available skills from which Skills_Matrix entries are drawn.
- **Work_Item**: A Jira issue retrieved from one or more configured Jira projects.
- **Merge_Request**: A GitLab merge request retrieved from one or more configured GitLab projects.
- **Ticket_Reference**: A Jira issue key (e.g. `PROJ-123`) detected in a Merge_Request's title, description, or source branch name.
- **Review_Threshold**: A configurable duration (in hours) after which an open Merge_Request is considered overdue for review.
- **Cache**: The Application's local data store holding the most recently fetched copies of external API data.
- **Background_Updater**: The Application component responsible for periodically refreshing the Cache from external APIs without user interaction.
- **Encryption_Layer**: The Application component responsible for encrypting sensitive data at rest.
- **API_Client**: The Application component that communicates with the Jira and GitLab APIs.
- **Dashboard**: A web page presenting aggregated, filtered, or summarised data to the user.
- **Credential_Store**: The secure, encrypted storage location for API tokens and other secrets.

---

## Requirements

### Requirement 1: Team Member Profiles

**User Story:** As a Team_Manager, I want to create and maintain profiles for each Team_Member, so that I have a single source of truth for who is on my team and what they are capable of.

#### Acceptance Criteria

1. THE Application SHALL provide a profile page for each Team_Member, displaying the Team_Member's name, username, and avatar photo.
2. WHEN a Team_Manager creates a new Team_Member profile, THE Application SHALL persist the profile and make it immediately accessible via the profile page without requiring a separate refresh or navigation action.
3. WHEN a Team_Manager updates a Team_Member's name, username, or avatar photo, THE Application SHALL reflect the updated values on the profile page within one page load.
4. IF a required profile field (name or username) is submitted as empty, THEN THE Application SHALL reject the submission and display a descriptive validation error indicating which specific field is missing.
5. THE Application SHALL restrict profile creation and modification to authenticated Team_Manager users.
6. IF a Team_Manager submits a username that matches an existing Team_Member's username, THEN THE Application SHALL reject the submission and display a descriptive error indicating the username is already in use.
7. WHEN a Team_Manager uploads an avatar photo, THE Application SHALL accept files in JPEG, PNG, GIF, and WebP formats up to 5 MB in size; IF the file exceeds 5 MB or is not one of the accepted formats, THEN THE Application SHALL reject the upload and display an error indicating the size limit and accepted formats.

---

### Requirement 2: Skills Matrix

**User Story:** As a Team_Manager, I want to record and update each Team_Member's skills against a shared catalogue, so that I can track current proficiency and define development aspirations.

#### Acceptance Criteria

1. THE Application SHALL maintain a Skill_Catalogue containing the list of available skills, editable only by authenticated Team_Manager users.
2. WHEN a skill is added to the Skill_Catalogue, THE Application SHALL make that skill available for assignment to any Skills_Matrix without requiring a restart.
3. WHEN a Team_Manager assigns a skill to a Team_Member, THE Application SHALL record both a current proficiency level and an optional aspiration level drawn from the defined set of levels: Beginner, Intermediate, Advanced, Expert.
4. WHEN a Team_Manager removes a skill from the Skill_Catalogue, THE Application SHALL retain existing Skills_Matrix entries that reference that skill and mark them as referencing a deprecated skill.
5. IF a submitted proficiency level is not one of the defined set of levels (Beginner, Intermediate, Advanced, Expert), THEN THE Application SHALL reject the submission, return a descriptive error indicating the valid levels, and leave the existing Skills_Matrix entry unchanged.
6. THE Application SHALL allow a Team_Manager to view, add, edit, and remove skills in a Team_Member's Skills_Matrix.
7. IF a Team_Manager attempts to add a skill to the Skill_Catalogue with a name that matches an existing skill name (case-insensitive), THEN THE Application SHALL reject the submission and display a descriptive error indicating the duplicate name.
8. WHEN a Team_Manager attempts to remove a skill from the Skill_Catalogue that has existing Skills_Matrix references, THE Application SHALL display a confirmation prompt indicating how many Team_Members reference that skill before proceeding with the removal.

---

### Requirement 3: Team Skills Dashboard

**User Story:** As a Team_Manager, I want a dashboard showing skills across the whole team, so that I can identify strengths, gaps, and development priorities at a glance.

#### Acceptance Criteria

1. THE Application SHALL provide a team-wide Skills Dashboard that aggregates the Skills_Matrix data for all Team_Members within the Team_Manager's configured team.
2. THE Skills Dashboard SHALL display each skill from the Skill_Catalogue alongside the count of Team_Members holding that skill at each of the four proficiency levels (Beginner, Intermediate, Advanced, Expert), showing a count of zero where no Team_Member holds a skill at a given level rather than omitting that level.
3. THE Skills Dashboard SHALL display, for each skill, the count of Team_Members whose aspiration level exceeds their current proficiency level, enabling identification of planned skill growth.
4. WHEN a Team_Member's Skills_Matrix is updated, THE Skills Dashboard SHALL reflect the updated data within one page load.
5. IF the Skills Dashboard fails to retrieve Skills_Matrix data, THEN THE Application SHALL display an error message and show the last successfully retrieved data where available, without displaying a blank or partially rendered dashboard.

---

### Requirement 4: Jira Work Item Integration

**User Story:** As a Team_Manager, I want to see all current Jira work items for my team in one place, so that I can monitor progress and identify blockers without switching between tools.

#### Acceptance Criteria

1. WHEN the Background_Updater runs, THE API_Client SHALL fetch Work_Items from all configured Jira projects and store the results in the Cache.
2. IF the API_Client fails to fetch Work_Items from a configured Jira project during a Background_Updater cycle, THEN THE Application SHALL retain the existing cached Work_Items for that project, record the failure without overwriting the cache, and log the failure with the project identifier and error details.
3. THE Application SHALL display each cached Work_Item showing at minimum: issue key, summary, assignee, status, and priority.
4. WHEN a Work_Item has a status of "Blocked" or contains a blocking link, THE Application SHALL display a distinct visual indicator (such as a badge or icon) on that Work_Item on all relevant Dashboards.
5. WHEN a Work_Item has a status of "In Review" or any status mapped to the "In Review" category in the configured Jira workflow, THE Application SHALL display a distinct visual indicator on that Work_Item on all relevant Dashboards that is visually different from the blocked indicator.
6. THE Application SHALL provide a Work_Items Dashboard showing all active Work_Items (those not in Done, Closed, or Cancelled status) for the team, filterable by assignee.
7. WHEN a Team_Manager selects an individual Work_Item, THE Application SHALL display the full Work_Item detail view, including description, comments, labels, and linked issues.
8. IF the Work_Item detail view fails to load, THEN THE Application SHALL display an error message indicating the failure and preserve the current Dashboard state without navigating away.

---

### Requirement 5: Work Item Reassignment

**User Story:** As a Team_Manager, I want to reassign Jira work items directly from the Application, so that I can rebalance workload without leaving the tool.

#### Acceptance Criteria

1. WHEN a Team_Manager selects a new assignee for a Work_Item and confirms, THE API_Client SHALL submit the reassignment request to the Jira API within 5 seconds of the confirmation.
2. WHEN the Jira API returns a success response for a reassignment, THE Application SHALL update the cached Work_Item to reflect the new assignee without waiting for the next Background_Updater cycle.
3. IF the Jira API returns an error response for a reassignment, THEN THE Application SHALL display a descriptive error message indicating the reassignment failed and leave the cached Work_Item unchanged.
4. IF the Jira API does not respond to a reassignment request within 10 seconds, THEN THE Application SHALL display a timeout error message and leave the cached Work_Item unchanged.
5. THE Application SHALL restrict Work_Item reassignment to authenticated Team_Manager users.
6. THE Application SHALL present only configured Team_Members as selectable assignees when reassigning a Work_Item.

---

### Requirement 6: GitLab Merge Request Integration

**User Story:** As a Team_Manager, I want to see all open merge requests for my team in one place, so that I can monitor review load and identify requests that need attention.

#### Acceptance Criteria

1. WHEN the Background_Updater runs, THE API_Client SHALL fetch open Merge_Requests from all configured GitLab projects and store the results in the Cache.
2. IF the API_Client fails to fetch Merge_Requests from a configured GitLab project during a Background_Updater cycle, THEN THE Application SHALL retain the existing cached Merge_Requests for that project, record the failure timestamp, and log the failure with the project identifier and error details.
3. THE Application SHALL display each cached Merge_Request showing at minimum: title, author, target branch, creation date, and current review status, where review status is one of: Awaiting Review, Changes Requested, or Approved.
4. WHEN a cached Merge_Request has been open longer than the configured Review_Threshold, THE Application SHALL display a coloured border or badge on that Merge_Request on the Merge_Requests Dashboard and individual Team_Member Dashboard views.
5. THE Application SHALL provide a Merge_Requests Dashboard showing all open Merge_Requests; WHEN a Team_Member filter is applied, THE Application SHALL display only Merge_Requests where the selected Team_Member is the author or a reviewer; WHEN no filter is applied, THE Application SHALL display all open Merge_Requests for the whole team.
6. THE Application SHALL provide a configurable Review_Threshold expressed in whole days, with a valid range of 1 to 30 days and a default value of 2 days, editable by authenticated Team_Manager users.

---

### Requirement 7: Jira–GitLab Ticket Linking

**User Story:** As a Team_Manager, I want merge requests to be automatically linked to their corresponding Jira tickets, so that I can trace work from ticket to code review without manual cross-referencing.

#### Acceptance Criteria

1. WHEN the Application processes a Merge_Request, THE Application SHALL search the Merge_Request's title, description, and source branch name for a Ticket_Reference matching the pattern of one or more uppercase letters, a hyphen, and one to six decimal digits (e.g. `ABC-123`), where the uppercase letter prefix matches a configured Jira project key.
2. WHEN a Ticket_Reference is found in a Merge_Request, THE Application SHALL display a navigable link to the corresponding Work_Item in the configured Jira instance alongside the Merge_Request.
3. WHEN a Merge_Request contains multiple distinct Ticket_References, THE Application SHALL display a navigable link for each referenced Work_Item; IF the same Ticket_Reference appears more than once, THE Application SHALL display a single link for that Work_Item.
4. WHEN no Ticket_Reference is found in a Merge_Request, THE Application SHALL display the Merge_Request without a ticket link and without raising an error.
5. IF the configured Jira instance is unreachable when resolving a Ticket_Reference, THEN THE Application SHALL display the Ticket_Reference text as an unavailable link and SHALL NOT block display of the Merge_Request.
6. IF a Ticket_Reference matches the configured pattern but the referenced Work_Item does not exist in Jira, THEN THE Application SHALL display the Ticket_Reference text without a navigable link and without raising an error.

---

### Requirement 8: Background Data Refresh

**User Story:** As a Team_Manager, I want the Application to keep its data current automatically, so that I can trust that what I see reflects the actual state of our tools without manually triggering refreshes.

#### Acceptance Criteria

1. THE Background_Updater SHALL refresh all configured Jira and GitLab data sources at a configurable interval between 1 and 60 minutes, with a default interval of 15 minutes.
2. WHILE the Background_Updater is running, THE Application SHALL continue to serve Dashboard pages using cached data with a response time no greater than the pre-refresh baseline.
3. WHEN the Background_Updater completes a refresh cycle, THE Application SHALL update the Cache with the latest data so that the next Dashboard load reflects the newly fetched data.
4. IF the Background_Updater encounters an API error during a refresh cycle, THEN THE Application SHALL log the error including the affected data source identifier and error details, retain the existing cached data, and attempt the refresh again at the next scheduled interval.
5. IF the Background_Updater fails to complete a successful refresh for a given data source for 3 or more consecutive cycles, THEN THE Application SHALL display a staleness warning on the Dashboard indicating that data for that source may be out of date.
6. THE Application SHALL display the timestamp of the last successful Cache refresh on each Dashboard, showing the date and time accurate to the nearest minute.

---

### Requirement 9: Local Caching

**User Story:** As a Team_Manager, I want the Application to serve data quickly from a local cache, so that Dashboards load fast even when external APIs are slow or temporarily unavailable.

#### Acceptance Criteria

1. THE Cache SHALL persist data to local storage such that a restart of the Application serves cached data before the first Background_Updater cycle completes.
2. WHEN the Application starts with existing cached data, THE Application SHALL serve Dashboard pages from that cached data within 2 seconds, before the first Background_Updater cycle completes.
3. WHEN external API data is unavailable, THE Application SHALL serve the most recently cached data and display a visual indicator that the data was last refreshed more than one Background_Updater cycle ago.
4. IF no cached data exists and external API data is unavailable at startup, THEN THE Application SHALL display an error message indicating that no data is available and prompt the Team_Manager to verify API configuration.
5. THE Application SHALL serve Dashboard pages from the Cache within 2 seconds without making a synchronous external API call during the page request.

---

### Requirement 10: Security and Credential Management

**User Story:** As a Team_Manager, I want the Application to handle credentials and sensitive data securely, so that API tokens and team data are not exposed to unauthorised parties.

#### Acceptance Criteria

1. THE Credential_Store SHALL encrypt all stored API tokens and secrets using an encryption algorithm with a minimum key length of 256 bits before writing them to disk.
2. THE Application SHALL never write API tokens, passwords, or authentication secrets to log output.
3. THE Application SHALL validate and sanitise all user-supplied input before using it in API calls, database queries, or rendered HTML output; IF input fails validation, THEN THE Application SHALL return a descriptive error indicating the reason without echoing the invalid value back to the user.
4. THE Application SHALL enforce authentication on all routes that expose team data or configuration; IF an unauthenticated or unauthorised request is made to a protected route, THEN THE Application SHALL return an HTTP 401 response that does not expose route details or data in the response body, and redirect the user to the login page.
5. WHEN a session expires or a user logs out, THE Application SHALL invalidate the session token server-side and require re-authentication before granting access.
6. THE Encryption_Layer SHALL encrypt sensitive Team_Member data (including Skills_Matrix records and profile details) at rest using an encryption algorithm with a minimum key length of 256 bits.
7. WHILE the Application is deployed in a non-localhost context, THE Application SHALL reject or redirect plain HTTP requests before any request data is processed, enforcing HTTPS for all communication between the browser and the Application server.
8. IF the Credential_Store fails to read or write credentials, THEN THE Application SHALL deny access to the affected feature, log the failure without exposing credential values, and SHALL NOT fall back to unencrypted storage or plaintext transmission.

---

### Requirement 11: Extensibility and Frontend Architecture

**User Story:** As a developer, I want the Application to use a structured, templated frontend architecture, so that new features and pages can be added consistently and without rework.

#### Acceptance Criteria

1. THE Application SHALL implement a templated frontend using a component or partial system that allows new pages to reuse existing layout, navigation, and styling elements without duplicating markup.
2. THE Application SHALL separate routing, business logic, and presentation concerns so that adding a new Dashboard page requires changes in no more than 3 distinct files.
3. THE Application SHALL expose an internal API layer between the frontend and the data access logic so that data sources can be swapped or extended without modifying frontend templates.
4. THE Application SHALL use semantic HTML elements (header, nav, main, section, article, footer) in all templates where the content matches the semantic meaning of those elements.
5. THE Application SHALL ensure all interactive elements are reachable and operable by keyboard with a visible focus indicator.
6. THE Application SHALL ensure all images include descriptive alt text of no more than 125 characters.
7. IF the internal API layer cannot reach a data source, THEN THE Application SHALL return a structured error response to the frontend template and display a user-facing error message without rendering a partially populated page.

---

### Requirement 12: Deployment Architecture

**User Story:** As a Team_Manager, I want to deploy the Application locally using standard container tooling, with a clear path to server-hosted deployment, so that setup is reproducible and the architecture can scale.

#### Acceptance Criteria

1. THE Application SHALL be deployable via Docker Compose with a single `docker-compose up` command on a developer workstation, with all services reachable and healthy within 120 seconds of that command completing.
2. THE Application SHALL provide Kubernetes manifests including at minimum a Deployment, a Service, and a ConfigMap sufficient to deploy the Application and its dependencies to a Kubernetes cluster.
3. THE Application SHALL externalise all environment-specific configuration (API endpoints, credentials, thresholds) through environment variables or mounted configuration files, with no hardcoded values in the image.
4. WHEN the Application starts, THE Application SHALL validate that all required configuration values are present and log a descriptive error indicating which value is missing, then exit with a non-zero exit code.
5. THE Application SHALL produce structured JSON log lines on stdout, where each line includes at minimum the fields: timestamp (ISO 8601), severity, and message.

---

### Requirement 13: Bulk Skills Import

**User Story:** As a Team_Manager, I want to bulk import Skills_Matrix entries for my Team_Members from a CSV file, so that I can populate or update the whole team's skills data in one step instead of entering each skill by hand.

#### Acceptance Criteria

1. THE Application SHALL provide a bulk import page where an authenticated Team_Manager can upload a CSV file of Skills_Matrix entries with a header row naming the columns `username`, `skill`, `current_level`, and optionally `aspiration_level` (column order and header case insensitive).
2. WHEN a Team_Manager uploads a CSV file in which every row is valid, THE Application SHALL create or update the Skills_Matrix entry for each row and display a summary including the number of entries imported and the number of Team_Members affected.
3. THE Application SHALL apply a bulk import atomically: IF any row fails validation, THEN THE Application SHALL import no rows, leave the Skills_Matrix and Skill_Catalogue unchanged, and display each failing row's number, field, and reason without echoing the invalid value.
4. WHEN the Team_Manager selects the "create missing skills" option, THE Application SHALL add skills referenced in the CSV that are not in the Skill_Catalogue (case-insensitive match) to the Skill_Catalogue as part of the same import; IF the option is not selected, THEN each row referencing an unknown skill SHALL be reported as a validation error.
5. IF a row references a username that does not match an existing Team_Member (case-insensitive), THEN THE Application SHALL report a validation error for that row.
6. IF a row's proficiency or aspiration level does not match one of the defined levels (Beginner, Intermediate, Advanced, Expert; case-insensitive), THEN THE Application SHALL report a validation error for that row indicating the valid levels.
7. IF the same username and skill combination appears in more than one row of the file, THEN THE Application SHALL report a validation error identifying both row numbers.
8. IF the uploaded file exceeds 1 MB, is not valid UTF-8 text, or does not contain the required header columns, THEN THE Application SHALL reject the import and display a descriptive error.
9. THE Application SHALL restrict bulk import to authenticated Team_Manager users.

---

### Requirement 14: Manual Data Refresh

**User Story:** As a Team_Manager, I want to trigger an immediate refresh of Jira and GitLab data from the dashboards, so that I can pull in the latest state on demand without waiting for the next Background_Updater cycle.

#### Acceptance Criteria

1. THE Application SHALL provide a manual refresh control on the Work_Items Dashboard (refreshing all enabled Jira projects) and on the Merge_Requests Dashboard (refreshing all enabled GitLab projects), available only to authenticated Team_Manager users.
2. WHEN a Team_Manager triggers a manual refresh, THE Application SHALL fetch data for every enabled project of the corresponding source, update the Cache, and record each project's refresh outcome exactly as a Background_Updater cycle would.
3. WHEN a manual refresh completes, THE Application SHALL display a summary including the number of projects refreshed and items fetched, and SHALL identify any project whose refresh failed.
4. IF the corresponding API URL or token is not configured, THEN THE Application SHALL display an error directing the Team_Manager to the Settings page and SHALL NOT record refresh failures against the configured projects.
5. IF a manual refresh fails for a project, THEN THE Application SHALL retain the existing cached data for that project unchanged (consistent with Requirements 4.2 and 6.2).
6. THE manual refresh SHALL run only in response to the explicit refresh action; dashboard page renders SHALL continue to make no synchronous external API calls (Requirement 9.5).

---

### Requirement 15: Password Management

**User Story:** As a Team_Manager, I want to change my password from the UI, so that I can rotate my credentials without editing environment variables and restarting the Application.

#### Acceptance Criteria

1. THE Application SHALL provide a change-password page for the authenticated Team_Manager that requires the current password, a new password, and a confirmation of the new password.
2. WHEN the submitted current password is correct, the new password is at least 8 characters long, and the confirmation matches the new password, THE Application SHALL store a salted hash of the new password in the encrypted database and apply it to subsequent logins immediately, without an application restart.
3. WHILE a stored password hash exists, THE Application SHALL use it for login verification in place of the TARZAN_ADMIN_PASSWORD environment value.
4. IF the current password is incorrect, the new password is shorter than 8 characters, or the confirmation does not match, THEN THE Application SHALL reject the change with a descriptive error, leave the existing password unchanged, and never echo any submitted password value.
5. WHEN the password is changed, THE Application SHALL invalidate all other active sessions for the Team_Manager server-side, keeping only the session that made the change.
6. THE Application SHALL never write submitted or stored password values to log output (per Requirement 10.2).
