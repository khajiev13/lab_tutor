import type { AgentState, SkillReview } from "@/features/market-demand/types";
import type { SelectionItem } from "@/features/market-demand/components/SelectionPanel";

// Helpers: treat null, [], and {} as "not set"
export function hasItems(v: unknown): boolean {
  if (v == null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return true;
}

type PendingSelection =
  | { kind: "job_groups"; items: SelectionItem[] }
  | null;

export function detectPendingSelection(state: AgentState): PendingSelection {
  // Job group selection: groups populated but no selection made yet
  if (hasItems(state.job_groups) && !hasItems(state.selected_jobs)) {
    const groups = state.job_groups!;
    const jobs = state.fetched_jobs;
    if (groups && jobs) {
      const items: SelectionItem[] = Object.entries(groups).map(
        ([name, indices]) => {
          const idxs = indices as number[];
          const companies = [
            ...new Set(
              idxs
                .map((i) => (jobs[i] as Record<string, string>)?.company)
                .filter(Boolean)
            ),
          ].slice(0, 3);
          const tooltipLines = idxs.map((i) => {
            const job = jobs[i] as Record<string, string>;
            const title = job?.title || "Untitled";
            const company = job?.company;
            return company ? `${title} — ${company}` : title;
          });
          return {
            id: name,
            label: name,
            description: companies.join(", "),
            count: idxs.length,
            tooltipLines,
          };
        }
      );
      if (items.length > 0) return { kind: "job_groups", items };
    }
  }

  return null;
}


export function resolveTeacherDecision(state: AgentState, review: SkillReview | null): "job_groups" | "skills" | "curriculum" | "working" {
 const pending = detectPendingSelection(state);
 if (pending) return pending.kind;
 if (review?.integration_review) return "curriculum";
 return review?.candidates.length ? "skills" : "working";
}
