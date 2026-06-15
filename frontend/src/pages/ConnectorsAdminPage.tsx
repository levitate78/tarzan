import { useEffect, useState } from "react";
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
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import SyncIcon from "@mui/icons-material/Sync";
import {
  useConnectors,
  useCreateConnector,
  useDeleteConnector,
  useReviewThreshold,
  useTriggerSync,
  useUpdateReviewThreshold,
} from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import type { ConnectorConfigCreate, ConnectorType } from "../api/types";

const EMPTY_CONNECTOR: ConnectorConfigCreate = {
  connector_type: "jira",
  base_url: "",
  token: "",
  project_keys: [],
  project_ids: [],
  poll_interval_seconds: 300,
};

function CreateConnectorDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState<ConnectorConfigCreate>(EMPTY_CONNECTOR);
  const [projectsRaw, setProjectsRaw] = useState("");
  const createConnector = useCreateConnector();

  useEffect(() => {
    if (open) {
      setForm(EMPTY_CONNECTOR);
      setProjectsRaw("");
    }
  }, [open]);

  async function handleSubmit() {
    const list = projectsRaw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const body: ConnectorConfigCreate =
      form.connector_type === "jira"
        ? { ...form, project_keys: list, project_ids: [] }
        : { ...form, project_ids: list.map(Number).filter((n) => !Number.isNaN(n)), project_keys: [] };
    try {
      await createConnector.mutateAsync(body);
      onClose();
    } catch {
      // error rendered inline
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add connector</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            select
            label="Type"
            value={form.connector_type}
            onChange={(e) => setForm((f) => ({ ...f, connector_type: e.target.value as ConnectorType }))}
          >
            <MenuItem value="jira">Jira</MenuItem>
            <MenuItem value="gitlab">GitLab</MenuItem>
          </TextField>
          <TextField
            label="Base URL"
            placeholder="https://your-company.atlassian.net"
            value={form.base_url}
            onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
            required
          />
          <TextField
            label="API token / PAT"
            type="password"
            value={form.token}
            onChange={(e) => setForm((f) => ({ ...f, token: e.target.value }))}
            helperText="Stored encrypted (AES-256-GCM) — never logged or displayed again."
            required
          />
          <TextField
            label={form.connector_type === "jira" ? "Project keys (comma separated)" : "Project IDs (comma separated)"}
            placeholder={form.connector_type === "jira" ? "PROJ, TEAM" : "123, 456"}
            value={projectsRaw}
            onChange={(e) => setProjectsRaw(e.target.value)}
          />
          <TextField
            label="Poll interval (seconds)"
            type="number"
            value={form.poll_interval_seconds}
            onChange={(e) => setForm((f) => ({ ...f, poll_interval_seconds: Number(e.target.value) }))}
            inputProps={{ min: 60 }}
          />
          {createConnector.isError && <Alert severity="error">{extractErrorMessage(createConnector.error)}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={handleSubmit} disabled={!form.base_url || !form.token || createConnector.isPending}>
          {createConnector.isPending ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function ReviewThresholdCard() {
  const { data, isLoading } = useReviewThreshold();
  const updateThreshold = useUpdateReviewThreshold();
  const [value, setValue] = useState<number>(24);

  useEffect(() => {
    if (data) setValue(data.threshold_hours);
  }, [data]);

  return (
    <Paper sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>
        Merge request review threshold
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Open merge requests older than this are flagged as "breached" across dashboards.
      </Typography>
      {isLoading ? (
        <CircularProgress size={24} />
      ) : (
        <Stack direction="row" spacing={2} alignItems="center">
          <TextField
            label="Threshold (hours)"
            type="number"
            size="small"
            value={value}
            onChange={(e) => setValue(Number(e.target.value))}
            inputProps={{ min: 1, step: 1 }}
          />
          <Button
            variant="contained"
            onClick={() => updateThreshold.mutate({ threshold_hours: value })}
            disabled={updateThreshold.isPending}
          >
            {updateThreshold.isPending ? "Saving…" : "Save"}
          </Button>
          {updateThreshold.isSuccess && <Chip color="success" label="Saved" size="small" />}
        </Stack>
      )}
      {updateThreshold.isError && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {extractErrorMessage(updateThreshold.error)}
        </Alert>
      )}
    </Paper>
  );
}

export function ConnectorsAdminPage() {
  const connectorsQuery = useConnectors();
  const deleteConnector = useDeleteConnector();
  const triggerSync = useTriggerSync();
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h4">Connectors</Typography>
        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<SyncIcon />}
            onClick={() => triggerSync.mutate()}
            disabled={triggerSync.isPending}
          >
            {triggerSync.isPending ? "Triggering…" : "Sync now"}
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
            Add connector
          </Button>
        </Stack>
      </Box>

      {triggerSync.isSuccess && <Alert severity="success">{triggerSync.data?.message}</Alert>}
      {triggerSync.isError && <Alert severity="error">{extractErrorMessage(triggerSync.error)}</Alert>}

      {connectorsQuery.isLoading ? (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
          <CircularProgress />
        </Box>
      ) : connectorsQuery.isError || !connectorsQuery.data ? (
        <Alert severity="error">{extractErrorMessage(connectorsQuery.error) || "Failed to load connectors"}</Alert>
      ) : (
        <Paper>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Type</TableCell>
                  <TableCell>Base URL</TableCell>
                  <TableCell>Projects</TableCell>
                  <TableCell>Poll interval</TableCell>
                  <TableCell>Last synced</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {connectorsQuery.data.map((c) => (
                  <TableRow key={c.id} hover>
                    <TableCell>
                      <Chip size="small" label={c.connector_type} />
                    </TableCell>
                    <TableCell>{c.base_url}</TableCell>
                    <TableCell>
                      {c.connector_type === "jira" ? c.project_keys.join(", ") : c.project_ids.join(", ")}
                    </TableCell>
                    <TableCell>{c.poll_interval_seconds}s</TableCell>
                    <TableCell>{c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : "Never"}</TableCell>
                    <TableCell>
                      <Chip size="small" color={c.is_healthy ? "success" : "error"} label={c.is_healthy ? "Healthy" : "Error"} />
                    </TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        onClick={() => {
                          if (window.confirm("Delete this connector configuration?")) {
                            deleteConnector.mutate(c.id);
                          }
                        }}
                      >
                        <DeleteIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
                {connectorsQuery.data.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} align="center">
                      <Typography color="text.secondary" sx={{ py: 2 }}>
                        No connectors configured yet.
                      </Typography>
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}

      {deleteConnector.isError && <Alert severity="error">{extractErrorMessage(deleteConnector.error)}</Alert>}

      <ReviewThresholdCard />

      <CreateConnectorDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
