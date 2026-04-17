/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useRef,
  type ReactNode,
} from "react";
import {
  fetchSkillDifficulty,
  fetchSkillPopularity,
  fetchClassMastery,
  fetchStudentGroups,
  type SkillDifficultyResponse,
  type SkillPopularityResponse,
  type ClassMasteryResponse,
  type StudentGroupsResponse,
} from "@/features/arcd-agent/api/teacher-twin";

const POLL_INTERVAL_MS = 30_000; // refresh class mastery every 30 s

// ── Context value ──────────────────────────────────────────────────────────

interface TeacherDataContextValue {
  courseId: number;
  loading: boolean;
  error: string;
  skillDifficulty: SkillDifficultyResponse | null;
  skillPopularity: SkillPopularityResponse | null;
  classMastery: ClassMasteryResponse | null;
  studentGroups: StudentGroupsResponse | null;
  lastUpdated: Date | null;
  refresh: () => void;
}

const TeacherDataContext = createContext<TeacherDataContextValue | null>(null);

export function useTeacherData(): TeacherDataContextValue {
  const ctx = useContext(TeacherDataContext);
  if (!ctx) throw new Error("useTeacherData must be used within TeacherDataProvider");
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────────────

interface TeacherDataProviderProps {
  children: ReactNode;
  courseId: string;
}

export function TeacherDataProvider({ children, courseId }: TeacherDataProviderProps) {
  const id = Number(courseId) || 0;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [skillDifficulty, setSkillDifficulty] = useState<SkillDifficultyResponse | null>(null);
  const [skillPopularity, setSkillPopularity] = useState<SkillPopularityResponse | null>(null);
  const [classMastery, setClassMastery] = useState<ClassMasteryResponse | null>(null);
  const [studentGroups, setStudentGroups] = useState<StudentGroupsResponse | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [version, setVersion] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    if (!id) {
      setError("No course selected.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [diff, pop, mastery, groups] = await Promise.all([
        fetchSkillDifficulty(id),
        fetchSkillPopularity(id),
        fetchClassMastery(id),
        fetchStudentGroups(id),
      ]);
      setSkillDifficulty(diff);
      setSkillPopularity(pop);
      setClassMastery(mastery);
      setStudentGroups(groups);
      setLastUpdated(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("401")) setError("SESSION_EXPIRED");
      else if (msg.includes("403")) setError("ACCESS_DENIED");
      else if (msg.includes("503")) setError("NEO4J_UNAVAILABLE");
      else setError("NETWORK_ERROR");
    } finally {
      setLoading(false);
    }
  }, [id, version]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load();
  }, [load]);

  // ── Live polling: refresh only class mastery every 30 s ───────────────────
  useEffect(() => {
    if (!id) return;
    pollRef.current = setInterval(async () => {
      try {
        const mastery = await fetchClassMastery(id);
        setClassMastery(mastery);
        setLastUpdated(new Date());
      } catch {
        // silently ignore poll errors — manual refresh still available
      }
    }, POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [id]);

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  return (
    <TeacherDataContext.Provider
      value={{
        courseId: id,
        loading,
        error,
        skillDifficulty,
        skillPopularity,
        classMastery,
        studentGroups,
        lastUpdated,
        refresh,
      }}
    >
      {children}
    </TeacherDataContext.Provider>
  );
}
