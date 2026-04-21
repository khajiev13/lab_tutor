export const SKILL_COLORS = [
  "var(--color-chart-1)",
  "var(--color-chart-2)",
  "var(--color-chart-3)",
  "var(--color-chart-4)",
  "var(--color-chart-5)",
  "var(--color-chart-6)",
  "var(--color-chart-7)",
  "var(--color-chart-8)",
  "var(--color-chart-9)",
  "var(--color-chart-10)",
];

export const SKILL_HEX = [
  "#f97316",
  "#06b6d4",
  "#8b5cf6",
  "#f43f5e",
  "#10b981",
  "#3b82f6",
  "#eab308",
  "#ec4899",
  "#14b8a6",
  "#a78bfa",
];

export const OVERALL_HEX = "#6366f1";

/** Canonical mastery tier thresholds used across all dashboard pages. */
export const MASTERY_TIERS = [
  { label: "Proficient",  min: 0.75, color: "#10b981" },
  { label: "Progressing", min: 0.50, color: "#3b82f6" },
  { label: "At-Risk",     min: 0.30, color: "#f59e0b" },
  { label: "Critical",    min: 0,    color: "#ef4444" },
] as const;

/** Return the tier color for a mastery value (0-1). */
export function masteryTierColor(m: number): string {
  if (m >= 0.75) return "#10b981";
  if (m >= 0.50) return "#3b82f6";
  if (m >= 0.30) return "#f59e0b";
  return "#ef4444";
}

/** Return the tier label for a mastery value (0-1). */
export function masteryTierLabel(m: number): string {
  if (m >= 0.75) return "Proficient";
  if (m >= 0.50) return "Progressing";
  if (m >= 0.30) return "At-Risk";
  return "Critical";
}
