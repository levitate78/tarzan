import { useEffect, useMemo, useState } from "react";
import Alert from "@mui/material/Alert";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Slider from "@mui/material/Slider";
import Snackbar from "@mui/material/Snackbar";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useAuth } from "../auth/AuthContext";
import { useSetUserSkills, useSkills, useUpdateUser, useUser } from "../api/hooks";
import { extractErrorMessage } from "../api/client";
import { LEVEL_LABELS } from "../components/SkillLevelDots";

interface SkillEdit {
  level: number;
  aspiration_level: number | null;
}

export function ProfilePage() {
  const { user: authUser, refreshUser } = useAuth();
  const userQuery = useUser(authUser?.id);
  const skillsQuery = useSkills();
  const updateUser = useUpdateUser(authUser?.id ?? "");
  const setSkills = useSetUserSkills(authUser?.id ?? "");

  const [profile, setProfile] = useState({
    full_name: "",
    avatar_url: "",
    gitlab_username: "",
    jira_username: "",
  });
  const [skillEdits, setSkillEdits] = useState<Record<string, SkillEdit>>({});
  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!userQuery.data) return;
    setProfile({
      full_name: userQuery.data.full_name,
      avatar_url: userQuery.data.avatar_url ?? "",
      gitlab_username: userQuery.data.gitlab_username ?? "",
      jira_username: userQuery.data.jira_username ?? "",
    });
    const edits: Record<string, SkillEdit> = {};
    for (const sl of userQuery.data.skill_levels) {
      edits[sl.skill.id] = { level: sl.level, aspiration_level: sl.aspiration_level ?? null };
    }
    setSkillEdits(edits);
  }, [userQuery.data]);

  const skillsByCategory = useMemo(() => {
    const map = new Map<string, typeof skillsQuery.data>();
    for (const skill of skillsQuery.data ?? []) {
      const list = map.get(skill.category) ?? [];
      list.push(skill);
      map.set(skill.category, list);
    }
    return map;
  }, [skillsQuery.data]);

  if (userQuery.isLoading || skillsQuery.isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 6 }}>
        <CircularProgress />
      </Box>
    );
  }

  if (userQuery.isError || !userQuery.data) {
    return <Alert severity="error">{extractErrorMessage(userQuery.error) || "Failed to load profile"}</Alert>;
  }

  async function handleSaveProfile() {
    try {
      await updateUser.mutateAsync({
        full_name: profile.full_name,
        avatar_url: profile.avatar_url || null,
        gitlab_username: profile.gitlab_username || null,
        jira_username: profile.jira_username || null,
      });
      await refreshUser();
      setSavedMessage("Profile updated");
    } catch {
      // error rendered inline below
    }
  }

  async function handleSaveSkills() {
    const payload = Object.entries(skillEdits)
      .filter(([, edit]) => edit.level > 0 || edit.aspiration_level !== null)
      .map(([skillId, edit]) => ({
        skill_id: skillId,
        level: edit.level,
        aspiration_level: edit.aspiration_level,
      }));
    try {
      await setSkills.mutateAsync(payload);
      setSavedMessage("Skills updated");
    } catch {
      // error rendered inline below
    }
  }

  function updateSkill(skillId: string, field: keyof SkillEdit, value: number | null) {
    setSkillEdits((prev) => ({
      ...prev,
      [skillId]: {
        level: prev[skillId]?.level ?? 0,
        aspiration_level: prev[skillId]?.aspiration_level ?? null,
        [field]: value,
      },
    }));
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <Stack direction="row" alignItems="center" spacing={2}>
        <Avatar src={profile.avatar_url || undefined} sx={{ width: 56, height: 56 }}>
          {profile.full_name.charAt(0)}
        </Avatar>
        <Box>
          <Typography variant="h4">{userQuery.data.full_name}</Typography>
          <Typography variant="body2" color="text.secondary">
            @{userQuery.data.username} · {userQuery.data.role}
          </Typography>
        </Box>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Profile details
        </Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Full name"
              fullWidth
              value={profile.full_name}
              onChange={(e) => setProfile((p) => ({ ...p, full_name: e.target.value }))}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Avatar URL"
              fullWidth
              value={profile.avatar_url}
              onChange={(e) => setProfile((p) => ({ ...p, avatar_url: e.target.value }))}
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="GitLab username"
              fullWidth
              value={profile.gitlab_username}
              onChange={(e) => setProfile((p) => ({ ...p, gitlab_username: e.target.value }))}
              helperText="Used to match merge requests authored / reviewed by you"
            />
          </Grid>
          <Grid item xs={12} sm={6}>
            <TextField
              label="Jira username"
              fullWidth
              value={profile.jira_username}
              onChange={(e) => setProfile((p) => ({ ...p, jira_username: e.target.value }))}
              helperText="Used to match Jira issues assigned to you"
            />
          </Grid>
        </Grid>
        {updateUser.isError && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {extractErrorMessage(updateUser.error)}
          </Alert>
        )}
        <Box sx={{ mt: 2 }}>
          <Button variant="contained" onClick={handleSaveProfile} disabled={updateUser.isPending}>
            {updateUser.isPending ? "Saving…" : "Save profile"}
          </Button>
        </Box>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" gutterBottom>
          Skills &amp; aspirations
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Set your current level for each skill, and optionally an aspiration level showing where
          you'd like to grow. These feed the team skills matrix.
        </Typography>

        {[...skillsByCategory.entries()].map(([category, skills]) => (
          <Box key={category} sx={{ mb: 3 }}>
            <Typography variant="subtitle2" sx={{ mb: 1, textTransform: "capitalize" }}>
              {category.replace("_", " ")}
            </Typography>
            <Grid container spacing={3}>
              {skills?.map((skill) => {
                const edit = skillEdits[skill.id] ?? { level: 0, aspiration_level: null };
                return (
                  <Grid item xs={12} sm={6} md={4} key={skill.id}>
                    <Typography variant="body2">{skill.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      Current: {LEVEL_LABELS[edit.level]}
                    </Typography>
                    <Slider
                      size="small"
                      value={edit.level}
                      min={0}
                      max={5}
                      step={1}
                      marks
                      onChange={(_, value) => updateSkill(skill.id, "level", value as number)}
                    />
                    <Typography variant="caption" color="text.secondary">
                      Aspiration: {edit.aspiration_level !== null ? LEVEL_LABELS[edit.aspiration_level] : "None set"}
                    </Typography>
                    <Slider
                      size="small"
                      color="secondary"
                      value={edit.aspiration_level ?? 0}
                      min={0}
                      max={5}
                      step={1}
                      marks
                      onChange={(_, value) =>
                        updateSkill(skill.id, "aspiration_level", (value as number) || null)
                      }
                    />
                  </Grid>
                );
              })}
            </Grid>
            <Divider sx={{ mt: 2 }} />
          </Box>
        ))}

        {setSkills.isError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {extractErrorMessage(setSkills.error)}
          </Alert>
        )}
        <Button variant="contained" onClick={handleSaveSkills} disabled={setSkills.isPending}>
          {setSkills.isPending ? "Saving…" : "Save skills"}
        </Button>
      </Paper>

      <Snackbar
        open={!!savedMessage}
        autoHideDuration={3000}
        onClose={() => setSavedMessage(null)}
        message={savedMessage}
      />
    </Box>
  );
}
