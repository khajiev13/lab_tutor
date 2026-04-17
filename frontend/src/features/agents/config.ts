import {
  BookOpen,
  TrendingUp,
  BookOpenText,
  Video,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

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
      "Add or modify real market skills from job postings. Analyze demand trends and map skills to your curriculum.",
    icon: TrendingUp,
    route: "market-analyst",
    enabled: true,
    color:
      "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400",
  },
  {
    id: "reading-agent",
    name: "Reading Agent",
    description:
      "Discovers the best online reading materials for every skill in your curriculum.",
    icon: BookOpenText,
    route: "reading-agent",
    enabled: true,
    color: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-400",
  },
  {
    id: "video-agent",
    name: "Video Agent",
    description:
      "Discovers the best YouTube videos for every skill in your curriculum.",
    icon: Video,
    route: "video-agent",
    enabled: true,
    color: "bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-400",
  },
  {
    id: "arcd",
    name: "ARCD Agent",
    description:
      "Adaptive Review & Cognitive Diagnosis — student profiling, learning path, review sessions, and digital twin.",
    icon: Sparkles,
    route: "arcd",
    enabled: true,
    color: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-400",
  },
];

export function getAgentById(id: string) {
  return AGENTS.find((a) => a.id === id);
}
