import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useMemberDashboard, useUser } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import { SkillLevelDots } from "../components/SkillLevelDots";

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

export function MemberDashboardPage() {
  const { userId } = useParams<{ userId: string }>();
  const dashboard = useMemberDashboard(userId);
  const userQuery = useUser(userId);

  if (dashboard.isLoading || userQuery.isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (dashboard.isError || userQuery.isError || !dashboard.data || !userQuery.data) {
    return (
      <Alert severity="error">
        {extractErrorMessage(dashboard.error || userQuery.error) || "Failed to load member dashboard"}
      </Alert>
    );
  }

  const { data: summary } = dashboard;
  const { data: user } = userQuery;

  const skillsByCategory = new Map<string, typeof user.skill_levels>();
  for (const sl of user.skill_levels) {
    const list = skillsByCategory.get(sl.skill.category) ?? [];
    list.push(sl);
    skillsByCategory.set(sl.skill.category, list);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Avatar src={user.avatar_url ?? undefined} sx={{ width: 56, height: 56 }}>
          {user.full_name.charAt(0)}
        </Avatar>
        <Box>
          <Typography variant="h4">{user.full_name}</Typography>
          <Typography variant="body2" color="text.secondary">
            @{user.username} · {user.role}
            {user.gitlab_username && ` · GitLab: ${user.gitlab_username}`}
            {user.jira_username && ` · Jira: ${user.jira_username}`}
          </Typography>
        </Box>
      </Stack>

      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Open work items" value={summary.open_issues} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Blocked items" value={summary.blocked_issues} color={summary.blocked_issues ? "error.main" : undefined} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Open merge requests" value={summary.open_mrs} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <StatCard label="Breached MRs" value={summary.breached_mrs} color={summary.breached_mrs ? "error.main" : undefined} />
        </Grid>
      </Grid>

      <Stack direction="row" spacing={2}>
        <Button
          component={RouterLink}
          to={`/issues?assignee_id=${user.id}`}
          variant="outlined"
        >
          View work items
        </Button>
        <Button
          component={RouterLink}
          to={`/merge-requests?user_id=${user.id}`}
          variant="outlined"
        >
          View merge requests
        </Button>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Skills
        </Typography>
        {user.skill_levels.length === 0 ? (
          <Typography color="text.secondary">No skill levels recorded yet.</Typography>
        ) : (
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Category</TableCell>
                  <TableCell>Skill</TableCell>
                  <TableCell>Level</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {[...skillsByCategory.entries()].flatMap(([category, levels]) =>
                  levels!.map((sl, idx) => (
                    <TableRow key={sl.skill.id}>
                      {idx === 0 ? (
                        <TableCell rowSpan={levels!.length}>
                          <Chip size="small" label={category} />
                        </TableCell>
                      ) : null}
                      <TableCell>{sl.skill.name}</TableCell>
                      <TableCell>
                        <SkillLevelDots level={sl.level} aspirationLevel={sl.aspiration_level} />
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Box>
  );
}
