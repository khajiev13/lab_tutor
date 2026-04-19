/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type {
  PortfolioData,
  DatasetPortfolio,
  StudentPortfolio,
  SkillInfo,
} from "@/features/arcd-agent/lib/types";

// ── API base URL ───────────────────────────────────────────────────────────

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

// ── Shape normalizer ───────────────────────────────────────────────────────
// Handles both the legacy single-dataset response shape (pre-multi-dataset)
// and the current multi-dataset shape returned by /diagnosis/arcd-portfolio.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeData(raw: any): PortfolioData {
  if (Array.isArray(raw.datasets)) {
    return raw as PortfolioData;
  }
  // Legacy: single-dataset shape from older backend versions
  return {
    generated_at: raw.generated_at ?? new Date().toISOString(),
    datasets: [
      {
        id: raw.id ?? "course",
        name: raw.name ?? "Course",
        model_info: raw.model_info,
        skills: raw.skills,
        students: raw.students,
      },
    ],
  };
}

// ── Context interface ──────────────────────────────────────────────────────

interface DataContextValue {
  portfolioData: PortfolioData | null;
  loading: boolean;
  error: string;
  activeDatasetId: string;
  setActiveDatasetId: (id: string) => void;
  currentDataset: DatasetPortfolio | null;
  selectedUid: string;
  setSelectedUid: (uid: string) => void;
  student: StudentPortfolio | null;
  skills: SkillInfo[];
  practiceSkill: { id: number; name: string } | null;
  setPracticeSkill: (skill: { id: number; name: string } | null) => void;
  viewMode: "student" | "teacher";
  setViewMode: (mode: "student" | "teacher") => void;
  refreshData: () => void;
  dataVersion: number;
}

const DataContext = createContext<DataContextValue | null>(null);

export function useData(): DataContextValue {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used within DataProvider");
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────────────

interface DataProviderProps {
  children: ReactNode;
  courseId?: string;
}

export function DataProvider({ children, courseId }: DataProviderProps) {
  const [portfolioData, setPortfolioData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [activeDatasetId, setActiveDatasetId] = useState("");
  const [selectedUid, setSelectedUid] = useState("");
  const [practiceSkill, setPracticeSkill] = useState<{ id: number; name: string } | null>(null);
  const [viewMode, setViewMode] = useState<"student" | "teacher">("student");
  const [dataVersion, setDataVersion] = useState(0);

  // Apply normalized portfolio and pick sensible defaults for dataset + student
  const applyPortfolio = useCallback(
    (data: PortfolioData, preserveSelection: boolean) => {
      setPortfolioData(data);
      if (!preserveSelection || !activeDatasetId) {
        const first = data.datasets[0];
        if (first) {
          setActiveDatasetId(first.id);
          setSelectedUid(first.students[0]?.uid ?? "");
        }
      }
    },
    [activeDatasetId],
  );

  // Fetch portfolio from the KG-backed backend (JWT-authenticated)
  const fetchPortfolio = useCallback(
    async (preserveSelection: boolean) => {
      if (!courseId) {
        setError("No course selected. Please navigate to a course first.");
        return;
      }

      const token = localStorage.getItem("access_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;

      try {
        const r = await fetch(`${API_BASE}/diagnosis/arcd-portfolio/${courseId}`, { headers });

        if (r.status === 401) {
          setError("SESSION_EXPIRED");
          return;
        }
        if (r.status === 403) {
          setError("ACCESS_DENIED");
          return;
        }
        if (r.status === 503) {
          setError("NEO4J_UNAVAILABLE");
          return;
        }
        if (!r.ok) {
          setError(`HTTP_${r.status}`);
          return;
        }

        const raw = await r.json();
        const data = normalizeData(raw);
        applyPortfolio(data, preserveSelection);
        setDataVersion((v) => v + 1);
        setError("");
      } catch {
        setError("NETWORK_ERROR");
      }
    },
    [applyPortfolio, courseId],
  );

  // Initial load + reload when courseId changes
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      await fetchPortfolio(false);
      if (!cancelled) setLoading(false);
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshData = useCallback(() => {
    fetchPortfolio(true);
  }, [fetchPortfolio]);

  // Derived values
  const currentDataset =
    portfolioData?.datasets.find((d) => d.id === activeDatasetId) ??
    portfolioData?.datasets[0] ??
    null;

  const skills = currentDataset?.skills ?? [];

  const student =
    currentDataset?.students.find((s) => s.uid === selectedUid) ??
    currentDataset?.students[0] ??
    null;

  const handleSetDatasetId = useCallback(
    (id: string) => {
      setActiveDatasetId(id);
      const ds = portfolioData?.datasets.find((d) => d.id === id);
      if (ds) setSelectedUid(ds.students[0]?.uid ?? "");
    },
    [portfolioData],
  );

  return (
    <DataContext.Provider
      value={{
        portfolioData,
        loading,
        error,
        activeDatasetId,
        setActiveDatasetId: handleSetDatasetId,
        currentDataset,
        selectedUid,
        setSelectedUid,
        student,
        skills,
        practiceSkill,
        setPracticeSkill,
        viewMode,
        setViewMode,
        refreshData,
        dataVersion,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}
