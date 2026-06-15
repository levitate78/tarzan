import { useSearchParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Link from "@mui/material/Link";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
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
import { useMergeRequests, useUsers } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import { BreachChip, MRStateChip } from "../components/StatusChips";

const STATE_OPTIONS = ["opened", "closed", "merged", "locked"];

export function MergeRequestsPage() {
  const [params, setParams] = useSearchParams();

  const state = params.get("state") ?? "opened";
  const breachedOnly = params.get("breached_only") === "true";
  const userId = params.get("user_id") ?? "";
  const page = Number(params.get("page") ?? "1");
  const pageSize = 20;

  const usersQuery = useUsers(1, 100);
  const mrsQuery = useMergeRequests({
    state,
    breached_only: breachedOnly || undefined,
    user_id: userId || undefined,
    page,
    page_size: pageSize,
  });

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

  const memberName = userId ? usersQuery.data?.items.find((u) => u.id === userId)?.full_name : undefined;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Typography variant="h4">Merge Requests</Typography>

      <Paper sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap alignItems="center">
          <TextField
            select
            label="State"
            size="small"
            value={state}
            onChange={(e) => updateParam("state", e.target.value)}
            sx={{ minWidth: 140 }}
          >
            {STATE_OPTIONS.map((s) => (
              <MenuItem key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            select
            label="Team member"
            size="small"
            value={userId}
            onChange={(e) => updateParam("user_id", e.target.value)}
            sx={{ minWidth: 200 }}
          >
            <MenuItem value="">Everyone</MenuItem>
            {usersQuery.data?.items.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.full_name}
              </MenuItem>
            ))}
          </TextField>

          <FormControlLabel
            control={
              <Switch
                checked={breachedOnly}
                onChange={(e) => updateParam("breached_only", e.target.checked ? "true" : "")}
              />
            }
            label="Breached only"
          />

          {memberName && <Chip label={`Member: ${memberName}`} onDelete={() => updateParam("user_id", "")} />}
        </Stack>
      </Paper>

      {mrsQuery.isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : mrsQuery.isError || !mrsQuery.data ? (
        <Alert severity="error">{extractErrorMessage(mrsQuery.error) || "Failed to load merge requests"}</Alert>
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>MR</TableCell>
                  <TableCell>Project</TableCell>
                  <TableCell>State</TableCell>
                  <TableCell>Author</TableCell>
                  <TableCell>Reviewers</TableCell>
                  <TableCell>Review age</TableCell>
                  <TableCell>Linked issues</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {mrsQuery.data.items.map((mr) => (
                  <TableRow key={mr.id} hover>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Link href={mr.web_url ?? undefined} target="_blank" rel="noopener noreferrer">
                        <Typography variant="body2" noWrap title={mr.title}>
                          !{mr.external_id} {mr.title}
                        </Typography>
                      </Link>
                    </TableCell>
                    <TableCell>{mr.project_name}</TableCell>
                    <TableCell>
                      <MRStateChip state={mr.state} />
                    </TableCell>
                    <TableCell>{mr.author_username ?? "—"}</TableCell>
                    <TableCell>{mr.reviewer_usernames.join(", ") || "—"}</TableCell>
                    <TableCell>
                      {mr.state === "opened" ? (
                        <BreachChip breached={mr.breached} ageHours={mr.review_age_hours} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    <TableCell>
                      {mr.linked_issues.length > 0
                        ? mr.linked_issues.map((issue) => (
                            <Tooltip key={issue.id} title={issue.summary}>
                              <Link href={issue.jira_url ?? undefined} target="_blank" rel="noopener noreferrer" sx={{ mr: 1 }}>
                                {issue.key} <OpenInNewIcon sx={{ fontSize: 12, verticalAlign: "middle" }} />
                              </Link>
                            </Tooltip>
                          ))
                        : mr.jira_issue_keys.join(", ") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {mrsQuery.data.items.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center">
                      <Typography color="text.secondary" sx={{ py: 2 }}>
                        No merge requests match these filters.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
          <TablePagination
            component="div"
            count={mrsQuery.data.total}
            page={page - 1}
            onPageChange={handlePageChange}
            rowsPerPage={pageSize}
            rowsPerPageOptions={[pageSize]}
          />
        </Paper>
      )}
    </Box>
  );
}
