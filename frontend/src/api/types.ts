// Types mirroring backend/app/schemas (and openapi.yaml).

export type UserRole = "admin" | "lead" | "member" | "viewer";

export type SkillCategory =
  | "languages"
  | "frameworks"
  | "cloud"
  | "databases"
  | "devops"
  | "testing"
  | "soft_skills"
  | "other";

export type IssueStatus =
  | "todo"
  | "in_progress"
  | "in_review"
  | "blocked"
  | "done"
  | "cancelled";

export type IssuePriority = "critical" | "high" | "medium" | "low";

export type MRState = "opened" | "closed" | "merged" | "locked";

export type ConnectorType = "jira" | "gitlab";

export interface PaginatedResponse<T> {
  total: number;
  page: number;
  page_size: number;
  items: T[];
}

// ── Skills ────────────────────────────────────────────────────────────────

export interface SkillResponse {
  id: string;
  name: string;
  category: SkillCategory;
  description: string | null;
  created_at: string;
}

export interface SkillCreate {
  name: string;
  category: SkillCategory;
  description?: string | null;
}

export interface SkillLevelResponse {
  skill: SkillResponse;
  level: number;
  aspiration_level: number | null;
  updated_at: string;
}

export interface SkillLevelSet {
  skill_id: string;
  level: number;
  aspiration_level?: number | null;
}

export interface TeamSkillsMatrix {
  skill: SkillResponse;
  member_count: number;
  average_level: number;
  gap_count: number;
  distribution: Record<string, number>;
}

// ── Users ─────────────────────────────────────────────────────────────────

export interface UserSummary {
  id: string;
  username: string;
  full_name: string;
  avatar_url: string | null;
  role: string;
}

export interface UserResponse {
  id: string;
  username: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
  gitlab_username: string | null;
  jira_username: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
  skill_levels: SkillLevelResponse[];
}

export interface UserCreate {
  username: string;
  email: string;
  full_name: string;
  password: string;
  avatar_url?: string | null;
  gitlab_username?: string | null;
  jira_username?: string | null;
  role?: UserRole;
}

export interface UserUpdate {
  full_name?: string;
  avatar_url?: string | null;
  gitlab_username?: string | null;
  jira_username?: string | null;
  role?: UserRole;
}

// ── Jira Issues ───────────────────────────────────────────────────────────

export interface GitLabMRSummary {
  id: string;
  external_id: number;
  project_name: string;
  title: string;
  state: MRState;
  web_url: string | null;
  review_age_hours: number;
  breached: boolean;
}

export interface JiraIssueResponse {
  id: string;
  key: string;
  project_key: string;
  summary: string;
  description: string | null;
  status: IssueStatus;
  priority: IssuePriority | null;
  issue_type: string;
  assignee: UserSummary | null;
  reporter_username: string | null;
  labels: string[];
  jira_url: string | null;
  jira_created_at: string | null;
  jira_updated_at: string | null;
  synced_at: string;
  linked_mrs?: GitLabMRSummary[];
}

export interface IssueReassignRequest {
  assignee_username: string;
}

// ── GitLab Merge Requests ─────────────────────────────────────────────────

export interface JiraIssueSummary {
  id: string;
  key: string;
  project_key: string;
  summary: string;
  status: IssueStatus;
  priority: IssuePriority | null;
  jira_url: string | null;
}

export interface GitLabMRResponse {
  id: string;
  external_id: number;
  project_id: number;
  project_name: string;
  title: string;
  description: string | null;
  state: MRState;
  author_username: string | null;
  assignee_usernames: string[];
  reviewer_usernames: string[];
  source_branch: string | null;
  target_branch: string | null;
  web_url: string | null;
  jira_issue_keys: string[];
  review_age_hours: number;
  breach_threshold_hours: number;
  breached: boolean;
  mr_created_at: string | null;
  mr_updated_at: string | null;
  synced_at: string;
  linked_issues: JiraIssueSummary[];
}

// ── Dashboard ─────────────────────────────────────────────────────────────

export interface MemberSummary {
  user: UserSummary;
  open_issues: number;
  blocked_issues: number;
  open_mrs: number;
  breached_mrs: number;
}

export interface TeamDashboard {
  total_members: number;
  total_open_issues: number;
  total_open_mrs: number;
  issues_by_status: Record<string, number>;
  mrs_breached: number;
  members: MemberSummary[];
}

// ── Connector Config ──────────────────────────────────────────────────────

export interface ConnectorConfigCreate {
  connector_type: ConnectorType;
  base_url: string;
  token: string;
  project_keys?: string[];
  project_ids?: number[];
  poll_interval_seconds?: number;
}

export interface ConnectorConfigResponse {
  id: string;
  connector_type: ConnectorType;
  base_url: string;
  project_keys: string[];
  project_ids: number[];
  poll_interval_seconds: number;
  last_synced_at: string | null;
  is_healthy: boolean;
  created_at: string;
}

// ── Review Threshold ──────────────────────────────────────────────────────

export interface ReviewThresholdResponse {
  threshold_hours: number;
}

export interface ReviewThresholdUpdate {
  threshold_hours: number;
}

// ── Auth ──────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}
