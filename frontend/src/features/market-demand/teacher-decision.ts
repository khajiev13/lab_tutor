import type { AgentState, ChatMessage, SkillReview } from "@/features/market-demand/types";
import type { SelectionItem } from "@/features/market-demand/components/SelectionPanel";

// Helpers: treat null, [], and {} as "not set"
export function hasItems(v: unknown): boolean {
  if (v == null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return true;
}

type PendingSelection =
  | { kind: "search_queries"; items: SelectionItem[] }
  | { kind: "job_groups"; items: SelectionItem[] }
  | null;

/** Extract quoted search terms from agent message text */
function extractSearchTerms(messages: ChatMessage[]): string[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i];
    if (msg.role !== "agent") continue;
    const text = msg.content;
    if (!text.includes("Search Terms") && !text.includes("search terms") && !text.includes("search queries")) continue;
    const matches = text.match(/"([^"]+)"/g);
    if (matches && matches.length >= 2) {
      return matches.map((m) => m.replace(/"/g, ""));
    }
    break;
  }
  return [];
}

export function detectPendingSelection(state: AgentState, messages: ChatMessage[]): PendingSelection {
  // Search query selection: agent proposed terms but no jobs fetched yet
  if (!hasItems(state.fetched_jobs)) {
    const terms = extractSearchTerms(messages);
    if (terms.length > 0) {
      return {
        kind: "search_queries",
        items: terms.map((term) => ({
          id: term,
          label: term,
        })),
      };
    }
  }

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


export function resolveTeacherDecision(state: AgentState, messages: ChatMessage[], review: SkillReview | null): "search_queries" | "job_groups" | "skills" | "curriculum" | "working" {
 const pending = detectPendingSelection(state, messages);
 if (pending) return pending.kind;
 if (review?.integration_review) return "curriculum";
 return review?.candidates.length ? "skills" : "working";
}
