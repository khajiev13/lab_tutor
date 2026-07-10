/**
 * Session-scoped, per-course UI state for the Teacher Twin tabs.
 *
 * Background: Radix `TabsContent` unmounts inactive panels by default. Any
 * component-local `useState` (Cohort sliders, What-If mode + manual skills,
 * Simulator filter, etc.) is therefore lost every time the teacher switches
 * tabs or navigates away from `/teacher-twin` and back. The user expectation
 * is "I should be able to flip between tabs/pages without restarting my
 * work, until I log out".
 *
 * This module mirrors the pattern in `teacherTwinSimulationStore.ts`:
 *   - Module-level `Map<courseId, state>` survives unmount/remount.
 *   - `useSyncExternalStore` keeps React in sync with external mutations.
 *   - `resetTeacherTwinUiState()` is called from `AuthContext` on logout,
 *     so a fresh login starts from defaults.
 *
 * Result objects (simulation/what-if responses) keep living in
 * `teacherTwinSimulationStore`. This store only owns *input* state.
 */

import { useCallback, useSyncExternalStore } from "react";

import type {
  AutomaticWhatIfFocus,
  WhatIfPlanningSource,
} from "@/features/arcd-agent/api/teacher-twin";

// Re-export so callers don't need to import from teacher-twin.ts just for the type.
export type { WhatIfPlanningSource };

export interface CohortUiState {
  steps: number;
  alpha: number;
  lambda: number;
  showBaseline: boolean;
  showIndividuals: boolean;
  mode: "groups" | "skills";
  selectedSkills: string[];
  expandedGroup: string | null;
}

export interface SimulatorUiState {
  simMode: "automatic" | "manual";
  topK: number;
  defaultMastery: number;
  selected: Record<string, number | null>;
  filter: string;
  showPairs: boolean;
}

export interface ManualSkillEntry {
  skill_name: string;
  current_avg_mastery: number;
  hypothetical_mastery: number;
}

export interface WhatIfUiState {
  analysisMode: "class" | "student";
  mode: "automatic" | "manual";
  automaticIntensity: number;
  automaticTopKHint: number;
  automaticFocus: AutomaticWhatIfFocus;
  topK: number;
  manualSkills: ManualSkillEntry[];
  selectedStudentId: number | null;
  studentMode: "automatic" | "manual";
  studentDelta: number;
  studentTopK: number;
}

export interface TeacherTwinUiState {
  activeTab: string;
  cohort: CohortUiState;
  simulator: SimulatorUiState;
  whatIf: WhatIfUiState;
}

const DEFAULT_COHORT: CohortUiState = {
  steps: 10,
  alpha: 0.15,
  lambda: 0.03,
  showBaseline: true,
  showIndividuals: false,
  mode: "groups",
  selectedSkills: [],
  expandedGroup: null,
};

const DEFAULT_SIMULATOR: SimulatorUiState = {
  simMode: "automatic",
  topK: 5,
  defaultMastery: 0.5,
  selected: {},
  filter: "",
  showPairs: false,
};

const DEFAULT_WHAT_IF: WhatIfUiState = {
  analysisMode: "class",
  mode: "automatic",
  automaticIntensity: 0.6,
  automaticTopKHint: 5,
  automaticFocus: "balanced",
  topK: 5,
  manualSkills: [],
  selectedStudentId: null,
  studentMode: "automatic",
  studentDelta: 0.2,
  studentTopK: 5,
};

const DEFAULT_UI_STATE: TeacherTwinUiState = {
  activeTab: "overview",
  cohort: DEFAULT_COHORT,
  simulator: DEFAULT_SIMULATOR,
  whatIf: DEFAULT_WHAT_IF,
};

const states = new Map<number, TeacherTwinUiState>();
const listeners = new Set<() => void>();

const emit = () => {
  listeners.forEach((listener) => listener());
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

const getState = (courseId: number): TeacherTwinUiState =>
  states.get(courseId) ?? DEFAULT_UI_STATE;

const setState = (courseId: number, next: TeacherTwinUiState) => {
  states.set(courseId, next);
  emit();
};

type Updater<T> = T | ((prev: T) => T);

function applyUpdater<T>(prev: T, updater: Updater<T>): T {
  return typeof updater === "function" ? (updater as (p: T) => T)(prev) : updater;
}

/**
 * Hook returning the current UI state for `courseId` plus stable setters
 * scoped to that course. The setters accept either a plain value or an
 * updater function (`React.Dispatch<SetStateAction<T>>`-shaped) so existing
 * `useState` call sites can swap in with minimal churn.
 */
export function useTeacherTwinUiState(courseId: number) {
  const state = useSyncExternalStore(
    subscribe,
    () => getState(courseId),
    () => getState(courseId),
  );

  const setActiveTab = useCallback(
    (next: Updater<string>) => {
      const current = getState(courseId);
      setState(courseId, { ...current, activeTab: applyUpdater(current.activeTab, next) });
    },
    [courseId],
  );

  const setCohort = useCallback(
    (next: Updater<CohortUiState>) => {
      const current = getState(courseId);
      setState(courseId, { ...current, cohort: applyUpdater(current.cohort, next) });
    },
    [courseId],
  );

  const setSimulator = useCallback(
    (next: Updater<SimulatorUiState>) => {
      const current = getState(courseId);
      setState(courseId, { ...current, simulator: applyUpdater(current.simulator, next) });
    },
    [courseId],
  );

  const setWhatIf = useCallback(
    (next: Updater<WhatIfUiState>) => {
      const current = getState(courseId);
      setState(courseId, { ...current, whatIf: applyUpdater(current.whatIf, next) });
    },
    [courseId],
  );

  return { state, setActiveTab, setCohort, setSimulator, setWhatIf };
}

/**
 * Clear cached UI state. Pass a `courseId` to clear a single course, or
 * omit to clear everything (used on logout).
 */
export function resetTeacherTwinUiState(courseId?: number) {
  if (typeof courseId === "number") {
    states.delete(courseId);
  } else {
    states.clear();
  }
  emit();
}
