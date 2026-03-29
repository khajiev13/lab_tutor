import { Bot, BrushCleaning, Map, Network, Search, type LucideIcon } from "lucide-react";
import type { AgentName } from "./types";

export interface AgentIdentity {
  displayName: string;
  shortName: string;
  icon: LucideIcon;
  accentColor: string;
  bgColor: string;
  borderColor: string;
}

export const AGENT_IDENTITIES: Record<AgentName, AgentIdentity> = {
  supervisor: {
    displayName: "Supervisor",
    shortName: "Supervisor",
    icon: Bot,
    accentColor: "text-blue-500",
    bgColor: "bg-blue-50 dark:bg-blue-950",
    borderColor: "border-blue-300 dark:border-blue-700",
  },
  skill_finder: {
    displayName: "Skill Finder",
    shortName: "Finder",
    icon: Search,
    accentColor: "text-violet-500",
    bgColor: "bg-violet-50 dark:bg-violet-950",
    borderColor: "border-violet-300 dark:border-violet-700",
  },
  curriculum_mapper: {
    displayName: "Curriculum Mapper",
    shortName: "Mapper",
    icon: Map,
    accentColor: "text-emerald-500",
    bgColor: "bg-emerald-50 dark:bg-emerald-950",
    borderColor: "border-emerald-300 dark:border-emerald-700",
  },
  skill_cleaner: {
    displayName: "Skill Cleaner",
    shortName: "Cleaner",
    icon: BrushCleaning,
    accentColor: "text-rose-500",
    bgColor: "bg-rose-50 dark:bg-rose-950",
    borderColor: "border-rose-300 dark:border-rose-700",
  },
  concept_linker: {
    displayName: "Concept Linker",
    shortName: "Linker",
    icon: Network,
    accentColor: "text-amber-500",
    bgColor: "bg-amber-50 dark:bg-amber-950",
    borderColor: "border-amber-300 dark:border-amber-700",
  },
};
