import { useEffect, useState } from "react";
import { coursesApi } from "@/features/courses/api";
import type { CourseMaterialsReadiness } from "@/features/courses/types";

const POLL_INTERVAL_MS = 10_000;

export function useCourseMaterialsReadiness(courseId: number, refreshTrigger: number, enabled: boolean) {
  const [result, setResult] = useState<{
    courseId: number;
    refreshTrigger: number;
    readiness: CourseMaterialsReadiness | null;
  } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      let readiness: CourseMaterialsReadiness | null = null;
      try {
        readiness = await coursesApi.getMaterialsReadiness(courseId);
      } catch { /* Keep launches disabled and check again automatically. */ }
      if (cancelled) return;
      setResult({courseId, refreshTrigger, readiness});
      timer = setTimeout(() => void refresh(), POLL_INTERVAL_MS);
    };
    void refresh();
    return () => {cancelled = true; clearTimeout(timer);};
  }, [courseId, refreshTrigger, enabled]);

  const current = result?.courseId === courseId && result.refreshTrigger === refreshTrigger ? result : null;
  return {
    ready: enabled && current?.readiness?.ready === true,
    message: current?.readiness?.message ?? (current
      ? "Course materials could not be checked. Checking again automatically…"
      : "Checking course materials…"),
  };
}
