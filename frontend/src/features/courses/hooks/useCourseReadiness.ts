import { useCallback, useEffect, useState } from "react";

import { coursesApi } from "@/features/courses/api";
import type { CourseReadiness } from "@/features/courses/types";

export function useCourseReadiness(courseId: number) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    courseId: number;
    attempt: number;
    readiness: CourseReadiness | null;
    error: boolean;
  } | null>(null);

  useEffect(() => {
    let active = true;
    coursesApi.getReadiness(courseId).then(
      (readiness) => {
        if (active) setResult({ courseId, attempt, readiness, error: false });
      },
      () => {
        if (active) setResult({ courseId, attempt, readiness: null, error: true });
      },
    );
    return () => { active = false; };
  }, [courseId, attempt]);

  const refresh = useCallback(() => setAttempt((value) => value + 1), []);
  const current = result?.courseId === courseId && result.attempt === attempt;

  return {
    readiness: current ? result.readiness : null,
    error: current && result.error,
    refresh,
  };
}
