import { useState } from "react";
import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
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
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import PersonAddIcon from "@mui/icons-material/PersonAdd";
import PersonOffIcon from "@mui/icons-material/PersonOff";
import { useCreateUser, useDeactivateUser, useUpdateUser, useUsers } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import { hasRole, useAuth } from "../auth/AuthContext";
import type { UserCreate, UserRole } from "../api/types";

const ROLES: UserRole[] = ["admin", "lead", "member", "viewer"];

function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createUser = useCreateUser();
  const [form, setForm] = useState<UserCreate>({
    username: "",
    email: "",
    full_name: "",
    password: "",
    gitlab_username: "",
    jira_username: "",
    role: "member",
  });

  async function handleSubmit() {
    try {
      await createUser.mutateAsync(form);
      onClose();
      setForm({ username: "", email: "", full_name: "", password: "", gitlab_username: "", jira_username: "", role: "member" });
    } catch {
      // error rendered inline
    }
  }

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add team member</DialogTitle>
      <DialogContent>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField label="Username" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} required />
          <TextField label="Full name" value={form.full_name} onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))} required />
          <TextField label="Email" type="email" value={form.email} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} required />
          <TextField
            label="Temporary password"
            type="password"
            value={form.password}
            onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            helperText="At least 12 characters. The user should change this after first login."
            required
          />
          <TextField label="GitLab username" value={form.gitlab_username ?? ""} onChange={(e) => setForm((f) => ({ ...f, gitlab_username: e.target.value }))} />
          <TextField label="Jira username" value={form.jira_username ?? ""} onChange={(e) => setForm((f) => ({ ...f, jira_username: e.target.value }))} />
          <TextField select label="Role" value={form.role} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as UserRole }))}>
            {ROLES.map((r) => (
              <MenuItem key={r} value={r}>
                {r}
              </MenuItem>
            ))}
          </TextField>
          {createUser.isError && <Alert severity="error">{extractErrorMessage(createUser.error)}</Alert>}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={createUser.isPending || !form.username || !form.email || !form.full_name || form.password.length < 12}
        >
          {createUser.isPending ? "Creating…" : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function RoleSelect({ userId, role }: { userId: string; role: string }) {
  const updateUser = useUpdateUser(userId);
  return (
    <TextField
      select
      size="small"
      value={role}
      onChange={(e) => updateUser.mutate({ role: e.target.value as UserRole })}
      disabled={updateUser.isPending}
      sx={{ minWidth: 110 }}
    >
      {ROLES.map((r) => (
        <MenuItem key={r} value={r}>
          {r}
        </MenuItem>
      ))}
    </TextField>
  );
}

export function TeamPage() {
  const { user } = useAuth();
  const isAdmin = hasRole(user?.role, "admin");
  const usersQuery = useUsers(1, 100);
  const deactivateUser = useDeactivateUser();
  const [createOpen, setCreateOpen] = useState(false);

  if (usersQuery.isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (usersQuery.isError || !usersQuery.data) {
    return <Alert severity="error">{extractErrorMessage(usersQuery.error) || "Failed to load team"}</Alert>;
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h4">Team</Typography>
        {isAdmin && (
          <Button variant="contained" startIcon={<PersonAddIcon />} onClick={() => setCreateOpen(true)}>
            Add member
          </Button>
        )}
      </Box>

      <Paper>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Member</TableCell>
                <TableCell>GitLab</TableCell>
                <TableCell>Jira</TableCell>
                <TableCell>Role</TableCell>
                {isAdmin && <TableCell align="right">Actions</TableCell>}
              </TableRow>
            </TableHead>
            <TableBody>
              {usersQuery.data.items.map((member) => (
                <TableRow key={member.id} hover>
                  <TableCell>
                    <Box
                      component={RouterLink}
                      to={`/team/${member.id}`}
                      sx={{ display: "flex", alignItems: "center", gap: 1, textDecoration: "none", color: "inherit" }}
                    >
                      <Avatar src={member.avatar_url ?? undefined} sx={{ width: 28, height: 28 }}>
                        {member.full_name.charAt(0)}
                      </Avatar>
                      <Box>
                        <Typography variant="body2">{member.full_name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          @{member.username}
                        </Typography>
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell>{member.gitlab_username ?? "—"}</TableCell>
                  <TableCell>{member.jira_username ?? "—"}</TableCell>
                  <TableCell>{isAdmin ? <RoleSelect userId={member.id} role={member.role} /> : <Chip size="small" label={member.role} />}</TableCell>
                  {isAdmin && (
                    <TableCell align="right">
                      <Tooltip title="Deactivate member">
                        <span>
                          <IconButton
                            size="small"
                            disabled={member.id === user?.id || deactivateUser.isPending}
                            onClick={() => {
                              if (window.confirm(`Deactivate ${member.full_name}?`)) {
                                deactivateUser.mutate(member.id);
                              }
                            }}
                          >
                            <PersonOffIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      {deactivateUser.isError && <Alert severity="error">{extractErrorMessage(deactivateUser.error)}</Alert>}

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </Box>
  );
}
