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
import EditIcon from "@mui/icons-material/Edit";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import { SkillsImportDialog } from "../components/SkillsImportDialog";
import { useCreateSkill, useDeleteSkill, useSkills, useUpdateSkill } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import type { SkillCategory, SkillCreate, SkillResponse } from "../api/types";

const CATEGORIES: SkillCategory[] = [
  "languages",
  "frameworks",
  "cloud",
  "databases",
  "devops",
  "testing",
  "soft_skills",
  "other",
];

const EMPTY_FORM: SkillCreate = { name: "", category: "languages", description: "" };

function SkillFormDialog({
  open,
  initial,
  onClose,
  onSubmit,
  submitting,
  error,
}: {
  open: boolean;
  initial: SkillCreate;
  onClose: () => void;
  onSubmit: (body: SkillCreate) => void;
  submitting: boolean;
  error: unknown;
}) {
  const [form, setForm] = useState<SkillCreate>(initial);

  useEffect(() => {
    if (open) setForm(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{initial.name ? "Edit skill" : "Add skill"}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            label="Name"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            required
          />
          <TextField
            select
            label="Category"
            value={form.category}
            onChange={(e) => setForm((f) => ({ ...f, category: e.target.value as SkillCategory }))}
          >
            {CATEGORIES.map((c) => (
              <MenuItem key={c} value={c}>
                {c.replace("_", " ")}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Description"
            multiline
            minRows={2}
            value={form.description ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
          {!!error && <Alert severity="error">{extractErrorMessage(error)}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={!form.name || submitting} onClick={() => onSubmit(form)}>
          {submitting ? "Saving…" : "Save"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export function SkillsAdminPage() {
  const skillsQuery = useSkills();
  const createSkill = useCreateSkill();
  const deleteSkill = useDeleteSkill();
  const [editing, setEditing] = useState<SkillResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [importing, setImporting] = useState(false);

  const updateSkill = useUpdateSkill(editing?.id ?? "");

  if (skillsQuery.isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (skillsQuery.isError || !skillsQuery.data) {
    return <Alert severity="error">{extractErrorMessage(skillsQuery.error) || "Failed to load skills"}</Alert>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h4">Skill Catalogue</Typography>
        <Box sx={{ display: "flex", gap: 1 }}>
          <Button variant="outlined" startIcon={<UploadFileIcon />} onClick={() => setImporting(true)}>
            Import CSV
          </Button>
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => setCreating(true)}>
            Add skill
          </Button>
        </Box>
      </Box>
      <Typography variant="body2" color="text.secondary">
        The canonical list of skills used across the team skills matrix and individual profiles.
      </Typography>

      <Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Description</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {skillsQuery.data.map((skill) => (
                <TableRow key={skill.id} hover>
                  <TableCell>{skill.name}</TableCell>
                  <TableCell>
                    <Chip size="small" label={skill.category.replace("_", " ")} />
                  </TableCell>
                  <TableCell>{skill.description ?? "—"}</TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => setEditing(skill)}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => {
                        if (window.confirm(`Delete skill "${skill.name}"? This removes it from all profiles.`)) {
                          deleteSkill.mutate(skill.id);
                        }
                      }}
                    >
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {deleteSkill.isError && <Alert severity="error">{extractErrorMessage(deleteSkill.error)}</Alert>}

      <SkillsImportDialog open={importing} onClose={() => setImporting(false)} />

      <SkillFormDialog
        open={creating}
        initial={EMPTY_FORM}
        onClose={() => setCreating(false)}
        onSubmit={async (body) => {
          try {
            await createSkill.mutateAsync(body);
            setCreating(false);
          } catch {
            // error rendered inline
          }
        }}
        submitting={createSkill.isPending}
        error={createSkill.error}
      />

      <SkillFormDialog
        open={!!editing}
        initial={editing ? { name: editing.name, category: editing.category, description: editing.description ?? "" } : EMPTY_FORM}
        onClose={() => setEditing(null)}
        onSubmit={async (body) => {
          try {
            await updateSkill.mutateAsync(body);
            setEditing(null);
          } catch {
            // error rendered inline
          }
        }}
        submitting={updateSkill.isPending}
        error={updateSkill.error}
      />
    </Box>
  );
}
