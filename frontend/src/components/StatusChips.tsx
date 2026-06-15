import Chip from "@mui/material/Chip";
import type { ChipProps } from "@mui/material/Chip";
import type { IssuePriority, IssueStatus, MRState } from "../api/types";

const STATUS_COLOR: Record<IssueStatus, ChipProps["color"]> = {
  todo: "default",
  in_progress: "info",
  in_review: "secondary",
  blocked: "error",
  done: "success",
  cancelled: "default",
};

const STATUS_LABEL: Record<IssueStatus, string> = {
  todo: "To do",
  in_progress: "In progress",
  in_review: "In review",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

export function IssueStatusChip({ status }: { status: IssueStatus | string }) {
  const key = status as IssueStatus;
  return (
    <Chip
      size="small"
      label={STATUS_LABEL[key] ?? status}
      color={STATUS_COLOR[key] ?? "default"}
      variant={key === "blocked" ? "filled" : "outlined"}
    />
  );
}

const PRIORITY_COLOR: Record<IssuePriority, ChipProps["color"]> = {
  critical: "error",
  high: "warning",
  medium: "info",
  low: "default",
};

export function IssuePriorityChip({ priority }: { priority: IssuePriority | string | null }) {
  if (!priority) return null;
  const key = priority as IssuePriority;
  return (
    <Chip
      size="small"
      label={priority.charAt(0).toUpperCase() + priority.slice(1)}
      color={PRIORITY_COLOR[key] ?? "default"}
      variant="outlined"
    />
  );
}

const MR_STATE_COLOR: Record<MRState, ChipProps["color"]> = {
  opened: "info",
  merged: "success",
  closed: "default",
  locked: "default",
};

export function MRStateChip({ state }: { state: MRState | string }) {
  const key = state as MRState;
  return (
    <Chip
      size="small"
      label={state.charAt(0).toUpperCase() + state.slice(1)}
      color={MR_STATE_COLOR[key] ?? "default"}
      variant="outlined"
    />
  );
}

export function BreachChip({ breached, ageHours }: { breached: boolean; ageHours: number }) {
  const formatted = ageHours < 1 ? `${Math.round(ageHours * 60)}m` : `${ageHours.toFixed(1)}h`;
  return (
    <Chip
      size="small"
      label={`${formatted} open${breached ? " — breached" : ""}`}
      color={breached ? "error" : "default"}
      variant={breached ? "filled" : "outlined"}
    />
  );
}
