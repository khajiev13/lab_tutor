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

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function normalizeData(raw: any): PortfolioData {
  if (Array.isArray(raw.datasets)) {
    return raw as PortfolioData;
  }
  return {
    generated_at: raw.generated_at ?? new Date().toISOString(),
    datasets: [
      {
        id: "xes3g5m",
        name: "XES3G5M",
        model_info: raw.model_info,
        skills: raw.skills,
        students: raw.students,
      },
    ],
  };
}

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
  dataSource: "api" | "static";
}

const DataContext = createContext<DataContextValue | null>(null);

export function useData(): DataContextValue {
  const ctx = useContext(DataContext);
  if (!ctx) throw new Error("useData must be used within DataProvider");
  return ctx;
}

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
  const [dataSource, setDataSource] = useState<"api" | "static">("static");

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

  const fetchPortfolio = useCallback(
    async (preserveSelection: boolean) => {
      // Try LAB_TUTOR backend with JWT auth
      if (courseId) {
        try {
          const token = localStorage.getItem("access_token");
          const headers: Record<string, string> = { "Content-Type": "application/json" };
          if (token) headers.Authorization = `Bearer ${token}`;

          const r = await fetch(`${API_BASE}/diagnosis/arcd-portfolio/${courseId}`, { headers });
          if (r.ok) {
            const raw = await r.json();
            const data = normalizeData(raw);
            applyPortfolio(data, preserveSelection);
            setDataSource("api");
            setDataVersion((v) => v + 1);
            setError("");
            return;
          }
          if (r.status === 401) {
            setError("Authentication required. Please log in again.");
            return;
          }
        } catch {
          // API not reachable — fall through to static
        }
      }

      // Fallback: static file
      try {
        const r = await fetch("/data/student_portfolio.json");
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const raw = await r.json();
        const data = normalizeData(raw);
        applyPortfolio(data, preserveSelection);
        setDataSource("static");
        setError("");
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [applyPortfolio, courseId],
  );

  useEffect(() => {
    fetchPortfolio(false).finally(() => setLoading(false));
  }, [courseId]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshData = useCallback(() => {
    fetchPortfolio(true);
  }, [fetchPortfolio]);

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
      if (ds) {
        setSelectedUid(ds.students[0]?.uid ?? "");
      }
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
        dataSource,
      }}
    >
      {children}
    </DataContext.Provider>
  );
}
