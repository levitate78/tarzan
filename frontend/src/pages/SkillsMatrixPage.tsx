import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useSkillsMatrix } from "../api/hooks";
import { extractErrorMessage } from "../api/client";

const LEVEL_LABELS = ["None", "Beginner", "Elementary", "Intermediate", "Advanced", "Expert"];

export function SkillsMatrixPage() {
  const { data, isLoading, isError, error } = useSkillsMatrix();

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (isError || !data) {
    return <Alert severity="error">{extractErrorMessage(error) || "Failed to load skills matrix"}</Alert>;
  }

  const byCategory = new Map<string, typeof data>();
  for (const row of data) {
    const list = byCategory.get(row.skill.category) ?? [];
    list.push(row);
    byCategory.set(row.skill.category, list);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Typography variant="h4">Team Skills Matrix</Typography>
      <Typography variant="body2" color="text.secondary">
        Aggregated skill levels across all active team members. "Gap" counts members whose aspiration
        level is higher than their current level — useful for spotting training opportunities. Edit
        your own levels and aspirations from your profile.
      </Typography>

      {data.length === 0 && (
        <Alert severity="info">No team members have recorded skill levels yet.</Alert>
      )}

      {[...byCategory.entries()].map(([category, rows]) => (
        <Paper key={category} sx={{ p: 2 }}>
          <Typography variant="h6" gutterBottom>
            {category.replace("_", " ")}
          </Typography>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Skill</TableCell>
                  <TableCell>Members</TableCell>
                  <TableCell>Average level</TableCell>
                  <TableCell>Distribution (0–5)</TableCell>
                  <TableCell>Gaps</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((row) => (
                  <TableRow key={row.skill.id}>
                    <TableCell>
                      <Typography variant="body2">{row.skill.name}</Typography>
                      {row.skill.description && (
                        <Typography variant="caption" color="text.secondary">
                          {row.skill.description}
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>{row.member_count}</TableCell>
                    <TableCell>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 120 }}>
                        <LinearProgress
                          variant="determinate"
                          value={(row.average_level / 5) * 100}
                          sx={{ flexGrow: 1, height: 8, borderRadius: 4 }}
                        />
                        <Typography variant="caption">{row.average_level.toFixed(1)}</Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: "flex", gap: 0.5 }}>
                        {Array.from({ length: 6 }, (_, level) => {
                          const count = row.distribution[String(level)] ?? 0;
                          const intensity = row.member_count > 0 ? count / row.member_count : 0;
                          return (
                            <Tooltip
                              key={level}
                              title={`${LEVEL_LABELS[level]}: ${count} member${count === 1 ? "" : "s"}`}
                            >
                              <Box
                                sx={{
                                  width: 28,
                                  height: 28,
                                  borderRadius: 1,
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontSize: 12,
                                  bgcolor:
                                    count === 0
                                      ? "action.hover"
                                      : `rgba(47, 111, 79, ${0.15 + intensity * 0.85})`,
                                  color: intensity > 0.5 ? "common.white" : "text.primary",
                                }}
                              >
                                {count || ""}
                              </Box>
                            </Tooltip>
                          );
                        })}
                      </Box>
                    </TableCell>
                    <TableCell>
                      {row.gap_count > 0 ? (
                        <Chip size="small" color="secondary" label={`${row.gap_count} aspiring`} />
                      ) : (
                        "—"
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      ))}
    </Box>
  );
}
