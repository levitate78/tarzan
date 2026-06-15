import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TablePagination from "@mui/material/TablePagination";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import { useIssues, useReassignIssue, useUsers } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import { hasRole, useAuth } from "../auth/AuthContext";
import { IssuePriorityChip, IssueStatusChip } from "../components/StatusChips";
import type { JiraIssueResponse } from "../api/types";

const STATUS_OPTIONS = ["todo", "in_progress", "in_review", "blocked", "done", "cancelled"];

function ReassignDialog({
  issue,
  onClose,
}: {
  issue: JiraIssueResponse | null;
  onClose: () => void;
}) {
  const [assignee, setAssignee] = useState("");
  const reassign = useReassignIssue(issue?.id ?? "");

  if (!issue) return null;

  async function handleSubmit() {
    try {
      await reassign.mutateAsync({ assignee_username: assignee });
      onClose();
    } catch {
      // error shown inline below
    }
  }

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Reassign {issue.key}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {issue.summary}
        </Typography>
        <TextField
          label="Jira username of new assignee"
          fullWidth
          margin="normal"
          value={assignee}
          onChange={(e) => setAssignee(e.target.value)}
          helperText="This updates the assignee directly in Jira."
        />
        {reassign.isError && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {extractErrorMessage(reassign.error)}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleSubmit} variant="contained" disabled={!assignee || reassign.isPending}>
          {reassign.isPending ? "Reassigning…" : "Reassign"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function IssuesPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const [reassignTarget, setReassignTarget] = useState<JiraIssueResponse | null>(null);

  const status = params.get("status") ?? "";
  const projectKey = params.get("project_key") ?? "";
  const assigneeId = params.get("assignee_id") ?? "";
  const page = Number(params.get("page") ?? "1");
  const pageSize = 20;

  const usersQuery = useUsers(1, 100);
  const issuesQuery = useIssues({
    status: status || undefined,
    project_key: projectKey || undefined,
    assignee_id: assigneeId || undefined,
    page,
    page_size: pageSize,
  });

  const canReassign = hasRole(user?.role, "lead");

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    next.set("page", "1");
    setParams(next);
  }

  function handlePageChange(_: unknown, newPage: number) {
    const next = new URLSearchParams(params);
    next.set("page", String(newPage + 1));
    setParams(next);
  }

  const assigneeName = assigneeId
    ? usersQuery.data?.items.find((u) => u.id === assigneeId)?.full_name
    : undefined;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="h4">Work Items</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField
            select
            label="Status"
            size="small"
            value={status}
            onChange={(e) => updateParam("status", e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">All statuses</MenuItem>
            {STATUS_OPTIONS.map((s) => (
              <MenuItem key={s} value={s}>
                {s.replace("_", " ")}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            label="Project key"
            size="small"
            value={projectKey}
            onChange={(e) => updateParam("project_key", e.target.value)}
            sx={{ minWidth: 140 }}
          />

          <TextField
            select
            label="Assignee"
            size="small"
            value={assigneeId}
            onChange={(e) => updateParam("assignee_id", e.target.value)}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="">Everyone</MenuItem>
            {usersQuery.data?.items.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.full_name}
              </MenuItem>
            ))}
          </TextField>

          {assigneeName && (
            <Chip label={`Assignee: ${assigneeName}`} onDelete={() => updateParam("assignee_id", "")} />
          )}
        </Stack>
      </Paper>

      {issuesQuery.isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : issuesQuery.isError || !issuesQuery.data ? (
        <Alert severity="error">{extractErrorMessage(issuesQuery.error) || "Failed to load work items"}</Alert>
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Key</TableCell>
                  <TableCell>Summary</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Priority</TableCell>
                  <TableCell>Assignee</TableCell>
                  <TableCell>Linked MRs</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {issuesQuery.data.items.map((issue) => (
                  <TableRow key={issue.id} hover>
                    <TableCell>
                      {issue.jira_url ? (
                        <Link href={issue.jira_url} target="_blank" rel="noopener noreferrer">
                          {issue.key}
                        </Link>
                      ) : (
                        issue.key
                      )}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 360 }}>
                      <Typography variant="body2" noWrap title={issue.summary}>
                        {issue.summary}
                      </Typography>
                    </TableCell>
                    <TableCell>
                      <IssueStatusChip status={issue.status} />
                    </TableCell>
                    <TableCell>
                      <IssuePriorityChip priority={issue.priority} />
                    </TableCell>
                    <TableCell>{issue.assignee ? issue.assignee.full_name : "Unassigned"}</TableCell>
                    <TableCell>
                      {issue.linked_mrs && issue.linked_mrs.length > 0
                        ? issue.linked_mrs.map((mr) => (
                            <Tooltip key={mr.id} title={mr.title}>
                              <Link
                                href={mr.web_url ?? undefined}
                                target="_blank"
                                rel="noopener noreferrer"
                                sx={{ mr: 1 }}
                              >
                                !{mr.external_id} <OpenInNewIcon sx={{ fontSize: 12, verticalAlign: "middle" }} />
                              </Link>
                            </Tooltip>
                          ))
                        : "—"}
                    </TableCell>
                    <TableCell align="right">
                      {canReassign && (
                        <Tooltip title="Reassign in Jira">
                          <IconButton size="small" onClick={() => setReassignTarget(issue)}>
                            <SwapHorizIcon fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {issuesQuery.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center">
                      <Typography color="text.secondary" sx={{ py: 2 }}>
                        No work items match these filters.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={issuesQuery.data.total}
            page={page - 1}
            onPageChange={handlePageChange}
            rowsPerPage={pageSize}
            rowsPerPageOptions={[pageSize]}
          />
        </Paper>
      )}

      <ReassignDialog issue={reassignTarget} onClose={() => setReassignTarget(null)} />
    </Box>
  );
}
