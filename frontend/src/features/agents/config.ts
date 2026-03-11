import { BookOpen, TrendingUp, type LucideIcon } from "lucide-react";

export interface AgentConfig {
  id: string;
  name: string;
  description: string;
  icon: LucideIcon;
  route: string;
  enabled: boolean;
  color: string; // Tailwind color class for avatar background
}

export const AGENTS: AgentConfig[] = [
  {
    id: "architect",
    name: "Curricular Alignment Architect",
    description:
      "Discovers, scores, and analyzes books aligned with your course materials.",
    icon: BookOpen,
    route: "architect",
    enabled: true,
    color: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-400",
  },
  {
    id: "market-analyst",
    name: "Market Demand Analyst",
    description:
      "Analyzes job market trends and maps course skills to industry demand.",
    icon: TrendingUp,
    route: "market-analyst",
    enabled: true,
    color:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  },
];

export function getAgentById(id: string) {
  return AGENTS.find((a) => a.id === id);
}
