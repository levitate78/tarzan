import Box from "@mui/material/Box";
import Tooltip from "@mui/material/Tooltip";

const MAX_LEVEL = 5;

const LEVEL_LABELS = ["None", "Beginner", "Elementary", "Intermediate", "Advanced", "Expert"];

/**
 * Renders a row of 5 dots representing a skill level (0-5). If an
 * aspiration level is provided and higher than the current level, the gap
 * dots are rendered as outlined to show the target.
 */
export function SkillLevelDots({
  level,
  aspirationLevel,
}: {
  level: number;
  aspirationLevel?: number | null;
}) {
  const target = aspirationLevel && aspirationLevel > level ? aspirationLevel : null;
  const label = `${LEVEL_LABELS[level] ?? level}${
    target ? ` (aspiring to ${LEVEL_LABELS[target] ?? target})` : ""
  }`;

  return (
    <Tooltip title={label}>
      <Box sx={{ display: "inline-flex", gap: 0.5, alignItems: "center" }}>
        {Array.from({ length: MAX_LEVEL }, (_, i) => {
          const dotLevel = i + 1;
          const filled = dotLevel <= level;
          const isTarget = !filled && target !== null && dotLevel <= target;
          return (
            <Box
              key={dotLevel}
              sx={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                bgcolor: filled ? "primary.main" : "transparent",
                border: (theme) =>
                  `1.5px ${isTarget ? "dashed" : "solid"} ${
                    filled
                      ? theme.palette.primary.main
                      : isTarget
                      ? theme.palette.secondary.main
                      : theme.palette.divider
                  }`,
              }}
            />
          );
        })}
      </Box>
    </Tooltip>
  );
}

export { LEVEL_LABELS };
