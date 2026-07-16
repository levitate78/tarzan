import { useMutation, useQuery, useQueryClient, type UseQueryOptions } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  ConnectorConfigCreate,
  ConnectorConfigResponse,
  GitLabMRResponse,
  IssueReassignRequest,
  JiraIssueResponse,
  MemberSummary,
  PaginatedResponse,
  ReviewThresholdResponse,
  ReviewThresholdUpdate,
  SkillCreate,
  SkillLevelResponse,
  SkillLevelSet,
  SkillResponse,
  SkillsImportRequest,
  SkillsImportResult,
  TeamDashboard,
  TeamSkillsMatrix,
  UserCreate,
  UserResponse,
  UserUpdate,
} from "./types";

// Default options shared by "live" dashboard-style queries: cache locally,
// but quietly refresh in the background so data stays fresh without a
// full-page reload.
const liveQueryOptions = {
  staleTime: 30_000,
  refetchInterval: 60_000,
  refetchOnWindowFocus: true,
} satisfies Partial<UseQueryOptions>;

// ── Dashboard ────────────────────────────────────────────────────────────

export function useTeamDashboard() {
  return useQuery({
    queryKey: ["dashboard", "team"],
    queryFn: async () => (await apiClient.get<TeamDashboard>("/dashboard/team")).data,
    ...liveQueryOptions,
  });
}

export function useMemberDashboard(userId: string | undefined) {
  return useQuery({
    queryKey: ["dashboard", "member", userId],
    queryFn: async () => (await apiClient.get<MemberSummary>(`/dashboard/member/${userId}`)).data,
    enabled: !!userId,
    ...liveQueryOptions,
  });
}

// ── Users ────────────────────────────────────────────────────────────────

export function useUsers(page = 1, pageSize = 50) {
  return useQuery({
    queryKey: ["users", page, pageSize],
    queryFn: async () =>
      (
        await apiClient.get<PaginatedResponse<UserResponse>>("/users", {
          params: { page, page_size: pageSize },
        })
      ).data,
    placeholderData: (prev) => prev,
    staleTime: 60_000,
  });
}

export function useUser(userId: string | undefined) {
  return useQuery({
    queryKey: ["users", userId],
    queryFn: async () => (await apiClient.get<UserResponse>(`/users/${userId}`)).data,
    enabled: !!userId,
    staleTime: 60_000,
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: UserCreate) => (await apiClient.post<UserResponse>("/users", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser(userId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: UserUpdate) => (await apiClient.patch<UserResponse>(`/users/${userId}`, body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["users", userId] });
    },
  });
}

export function useDeactivateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (userId: string) => {
      await apiClient.delete(`/users/${userId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useSetUserSkills(userId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SkillLevelSet[]) =>
      (await apiClient.put<SkillLevelResponse[]>(`/users/${userId}/skills`, body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users", userId] });
      qc.invalidateQueries({ queryKey: ["skills", "matrix"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

// ── Skills ───────────────────────────────────────────────────────────────

export function useSkills(category?: string) {
  return useQuery({
    queryKey: ["skills", category ?? "all"],
    queryFn: async () =>
      (await apiClient.get<SkillResponse[]>("/skills", { params: category ? { category } : {} })).data,
    staleTime: 5 * 60_000,
  });
}

export function useSkillsMatrix() {
  return useQuery({
    queryKey: ["skills", "matrix"],
    queryFn: async () => (await apiClient.get<TeamSkillsMatrix[]>("/skills/matrix")).data,
    ...liveQueryOptions,
  });
}

export function useCreateSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SkillCreate) => (await apiClient.post<SkillResponse>("/skills", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });
}

export function useUpdateSkill(skillId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SkillCreate) => (await apiClient.patch<SkillResponse>(`/skills/${skillId}`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });
}

export function useDeleteSkill() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (skillId: string) => {
      await apiClient.delete(`/skills/${skillId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["skills"] }),
  });
}

export function useImportSkillLevels() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SkillsImportRequest) =>
      (await apiClient.post<SkillsImportResult>("/skills/import", body)).data,
    onSuccess: () => {
      // Imports touch the catalogue, member profiles, and matrix aggregates.
      qc.invalidateQueries({ queryKey: ["skills"] });
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

// ── Jira Issues ──────────────────────────────────────────────────────────

export interface IssueFilters {
  assignee_id?: string;
  status?: string;
  project_key?: string;
  page?: number;
  page_size?: number;
}

export function useIssues(filters: IssueFilters) {
  return useQuery({
    queryKey: ["issues", filters],
    queryFn: async () =>
      (await apiClient.get<PaginatedResponse<JiraIssueResponse>>("/issues", { params: filters })).data,
    placeholderData: (prev) => prev,
    ...liveQueryOptions,
  });
}

export function useIssue(issueId: string | undefined) {
  return useQuery({
    queryKey: ["issues", "detail", issueId],
    queryFn: async () => (await apiClient.get<JiraIssueResponse>(`/issues/${issueId}`)).data,
    enabled: !!issueId,
  });
}

export function useReassignIssue(issueId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: IssueReassignRequest) =>
      (await apiClient.post<JiraIssueResponse>(`/issues/${issueId}/reassign`, body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["issues"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

// ── GitLab Merge Requests ────────────────────────────────────────────────

export interface MRFilters {
  author?: string;
  reviewer?: string;
  state?: string;
  breached_only?: boolean;
  user_id?: string;
  page?: number;
  page_size?: number;
}

export function useMergeRequests(filters: MRFilters) {
  return useQuery({
    queryKey: ["merge-requests", filters],
    queryFn: async () =>
      (await apiClient.get<PaginatedResponse<GitLabMRResponse>>("/merge-requests", { params: filters })).data,
    placeholderData: (prev) => prev,
    ...liveQueryOptions,
  });
}

// ── Config: connectors & review threshold ───────────────────────────────

export function useConnectors() {
  return useQuery({
    queryKey: ["config", "connectors"],
    queryFn: async () => (await apiClient.get<ConnectorConfigResponse[]>("/config/connectors")).data,
    staleTime: 30_000,
  });
}

export function useCreateConnector() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ConnectorConfigCreate) =>
      (await apiClient.post<ConnectorConfigResponse>("/config/connectors", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config", "connectors"] }),
  });
}

export function useUpdateConnector(configId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ConnectorConfigCreate) =>
      (await apiClient.put<ConnectorConfigResponse>(`/config/connectors/${configId}`, body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config", "connectors"] }),
  });
}

export function useDeleteConnector() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (configId: string) => {
      await apiClient.delete(`/config/connectors/${configId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config", "connectors"] }),
  });
}

export function useReviewThreshold() {
  return useQuery({
    queryKey: ["config", "review-threshold"],
    queryFn: async () => (await apiClient.get<ReviewThresholdResponse>("/config/review-threshold")).data,
    staleTime: 60_000,
  });
}

export function useUpdateReviewThreshold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ReviewThresholdUpdate) =>
      (await apiClient.put<ReviewThresholdResponse>("/config/review-threshold", body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["config", "review-threshold"] }),
  });
}

export function useTriggerSync() {
  return useMutation({
    mutationFn: async () => (await apiClient.post<{ message: string }>("/config/sync")).data,
  });
}
