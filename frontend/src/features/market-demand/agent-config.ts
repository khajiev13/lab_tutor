import { Bot, type LucideIcon } from "lucide-react";
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
  curriculum_mapper: {
    displayName: "Curriculum Mapper",
    shortName: "Mapper",
    icon: Bot,
    accentColor: "text-emerald-500",
    bgColor: "bg-emerald-50 dark:bg-emerald-950",
    borderColor: "border-emerald-300 dark:border-emerald-700",
  },
  concept_linker: {
    displayName: "Concept Linker",
    shortName: "Linker",
    icon: Bot,
    accentColor: "text-amber-500",
    bgColor: "bg-amber-50 dark:bg-amber-950",
    borderColor: "border-amber-300 dark:border-amber-700",
  },
};
