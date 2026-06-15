import { Link as RouterLink } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from "recharts";
import { useTeamDashboard } from "../api/hooks";
import { extractErrorMessage } from "../api/client";

const STATUS_LABELS: Record<string, string> = {
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="body2" color="text.secondary">
          {label}
        </Typography>
        <Typography variant="h4" sx={{ color }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  );
}

export function TeamDashboardPage() {
  const { data, isLoading, isError, error } = useTeamDashboard();

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !data) {
    return <Alert severity="error">{extractErrorMessage(error) || "Failed to load dashboard"}</Alert>;
  }

  const statusData = Object.entries(data.issues_by_status).map(([status, count]) => ({
    status: STATUS_LABELS[status] ?? status,
    count,
  }));

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Typography variant="h4">Team Dashboard</Typography>

      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Team members" value={data.total_members} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Open work items" value={data.total_open_issues} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Open merge requests" value={data.total_open_mrs} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="MRs needing review (breached)" value={data.mrs_breached} color="error.main" />
        </Grid>
      </Grid>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Work items by status
        </Typography>
        <Box sx={{ width: "100%", height: 280 }}>
          <ResponsiveContainer>
            <BarChart data={statusData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="status" />
              <YAxis allowDecimals={false} />
              <RechartsTooltip />
              <Bar dataKey="count" fill="#2f6f4f" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Team members
        </Typography>
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Member</TableCell>
                <TableCell align="right">Open issues</TableCell>
                <TableCell align="right">Blocked</TableCell>
                <TableCell align="right">Open MRs</TableCell>
                <TableCell align="right">Breached MRs</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.members.map((member) => (
                <TableRow
                  key={member.user.id}
                  hover
                  component={RouterLink}
                  to={`/team/${member.user.id}`}
                  sx={{ textDecoration: "none", cursor: "pointer" }}
                >
                  <TableCell>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Avatar src={member.user.avatar_url ?? undefined} sx={{ width: 28, height: 28 }}>
                        {member.user.full_name.charAt(0)}
                      </Avatar>
                      <Box>
                        <Typography variant="body2">{member.user.full_name}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          @{member.user.username}
                        </Typography>
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell align="right">{member.open_issues}</TableCell>
                  <TableCell align="right">
                    {member.blocked_issues > 0 ? (
                      <Chip size="small" color="error" label={member.blocked_issues} />
                    ) : (
                      member.blocked_issues
                    )}
                  </TableCell>
                  <TableCell align="right">{member.open_mrs}</TableCell>
                  <TableCell align="right">
                    {member.breached_mrs > 0 ? (
                      <Chip size="small" color="error" label={member.breached_mrs} />
                    ) : (
                      member.breached_mrs
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
}
