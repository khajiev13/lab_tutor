import { useSyncExternalStore } from "react";

import type {
  MultiSkillSimulationRequest,
  MultiSkillSimulationResponse,
  WhatIfRequest,
  WhatIfResponse,
} from "@/features/arcd-agent/api/teacher-twin";

export type TeacherTwinTaskStatus = "idle" | "running" | "success" | "error";

export interface TeacherTwinTaskState<Request, Result> {
  status: TeacherTwinTaskStatus;
  request: Request | null;
  result: Result | null;
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
}

function createInitialState<Request, Result>(): TeacherTwinTaskState<Request, Result> {
  return {
    status: "idle",
    request: null,
    result: null,
    error: null,
    startedAt: null,
    finishedAt: null,
  };
}

function createCourseTaskStore<Request, Result>() {
  const emptyState = createInitialState<Request, Result>();
  const states = new Map<number, TeacherTwinTaskState<Request, Result>>();
  const activeRuns = new Map<number, Promise<Result>>();
  const listeners = new Set<() => void>();

  const emit = () => {
    listeners.forEach((listener) => listener());
  };

  const getState = (courseId: number): TeacherTwinTaskState<Request, Result> =>
    states.get(courseId) ?? emptyState;

  const setState = (courseId: number, next: TeacherTwinTaskState<Request, Result>) => {
    states.set(courseId, next);
    emit();
  };

  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  };

  const run = (courseId: number, request: Request, task: () => Promise<Result>): Promise<Result> => {
    const activeRun = activeRuns.get(courseId);
    if (activeRun) return activeRun;

    setState(courseId, {
      status: "running",
      request,
      result: getState(courseId).result,
      error: null,
      startedAt: Date.now(),
      finishedAt: null,
    });

    const promise = task()
      .then((result) => {
        if (activeRuns.get(courseId) === promise) {
          activeRuns.delete(courseId);
          setState(courseId, {
            status: "success",
            request,
            result,
            error: null,
            startedAt: getState(courseId).startedAt,
            finishedAt: Date.now(),
          });
        }
        return result;
      })
      .catch((error: unknown) => {
        if (activeRuns.get(courseId) === promise) {
          activeRuns.delete(courseId);
          setState(courseId, {
            status: "error",
            request,
            result: null,
            error: error instanceof Error ? error.message : String(error),
            startedAt: getState(courseId).startedAt,
            finishedAt: Date.now(),
          });
        }
        throw error;
      });

    activeRuns.set(courseId, promise);
    return promise;
  };

  const reset = (courseId?: number) => {
    if (typeof courseId === "number") {
      activeRuns.delete(courseId);
      states.delete(courseId);
      emit();
      return;
    }
    activeRuns.clear();
    states.clear();
    emit();
  };

  return { getState, subscribe, run, reset };
}

const skillSimulationStore =
  createCourseTaskStore<MultiSkillSimulationRequest, MultiSkillSimulationResponse>();
const whatIfStore = createCourseTaskStore<WhatIfRequest, WhatIfResponse>();

function useCourseTaskState<Request, Result>(
  store: ReturnType<typeof createCourseTaskStore<Request, Result>>,
  courseId: number,
): TeacherTwinTaskState<Request, Result> {
  return useSyncExternalStore(
    store.subscribe,
    () => store.getState(courseId),
    () => store.getState(courseId),
  );
}

export function useTeacherTwinSkillSimulationTask(courseId: number) {
  return useCourseTaskState(skillSimulationStore, courseId);
}

export function startTeacherTwinSkillSimulationTask(
  courseId: number,
  request: MultiSkillSimulationRequest,
  task: () => Promise<MultiSkillSimulationResponse>,
) {
  return skillSimulationStore.run(courseId, request, task);
}

export function useTeacherTwinWhatIfTask(courseId: number) {
  return useCourseTaskState(whatIfStore, courseId);
}

export function startTeacherTwinWhatIfTask(
  courseId: number,
  request: WhatIfRequest,
  task: () => Promise<WhatIfResponse>,
) {
  return whatIfStore.run(courseId, request, task);
}

export function resetTeacherTwinSimulationTasks(courseId?: number) {
  skillSimulationStore.reset(courseId);
  whatIfStore.reset(courseId);
}
