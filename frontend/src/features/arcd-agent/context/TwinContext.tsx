/* eslint-disable react-refresh/only-export-components */
/**
 * TwinContext provides TwinViewerData to the dashboard.
 * Re-fetches automatically when `selectedUid` or `dataVersion` changes
 * so twin data stays in sync with mastery updates from review sessions.
 */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import type { TwinViewerData } from "@/features/arcd-agent/lib/types";

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

interface TwinContextValue {
  twinData: TwinViewerData | null;
  twinLoading: boolean;
  twinError: string | null;
  twinMatched: boolean;
  twinSource: "api" | "static" | null;
  checkReplan: (deviations: Array<{ delta: number }>) => boolean;
}

const TwinContext = createContext<TwinContextValue>({
  twinData: null,
  twinLoading: false,
  twinError: null,
  twinMatched: false,
  twinSource: null,
  checkReplan: () => false,
});

export function useTwin(): TwinContextValue {
  return useContext(TwinContext);
}

interface TwinProviderProps {
  children: ReactNode;
  selectedUid: string;
  dataVersion: number;
  courseId?: string;
}

export function TwinProvider({ children, selectedUid, dataVersion, courseId }: TwinProviderProps) {
  const [twinData, setTwinData] = useState<TwinViewerData | null>(null);
  const [twinLoading, setTwinLoading] = useState(true);
  const [twinError, setTwinError] = useState<string | null>(null);
  const [twinMatched, setTwinMatched] = useState(false);
  const [twinSource, setTwinSource] = useState<"api" | "static" | null>(null);

  useEffect(() => {
    if (!selectedUid) {
      setTwinLoading(false);
      return;
    }

    let cancelled = false;
    setTwinLoading(true);

    async function load() {
      // 1. Try LAB_TUTOR backend with JWT auth
      if (courseId) {
        try {
          const token = localStorage.getItem("access_token");
          const headers: Record<string, string> = { "Content-Type": "application/json" };
          if (token) headers.Authorization = `Bearer ${token}`;

          const resp = await fetch(`${API_BASE}/diagnosis/arcd-twin/${courseId}`, { headers });
          if (!cancelled && resp.ok) {
            const data = (await resp.json()) as TwinViewerData;
            if (data.current_twin) {
              setTwinData(data);
              setTwinMatched(true);
              setTwinSource("api");
              setTwinError(null);
              setTwinLoading(false);
              return;
            }
          }
        } catch {
          /* fall through to static */
        }
      }

      // 2. Fall back to static twin_viewer.json
      try {
        const r = await fetch("/data/twin_viewer.json");
        if (!cancelled) {
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          const data = (await r.json()) as TwinViewerData;
          const matched = String(data.student_id) === String(selectedUid);
          setTwinData(matched ? data : null);
          setTwinMatched(matched);
          setTwinSource(matched ? "static" : null);
          setTwinError(null);
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setTwinData(null);
          setTwinMatched(false);
          setTwinSource(null);
          setTwinError(e instanceof Error ? e.message : "Unknown error");
        }
      } finally {
        if (!cancelled) setTwinLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [selectedUid, dataVersion, courseId]);

  return (
    <TwinContext.Provider
      value={{
        twinData,
        twinLoading,
        twinError,
        twinMatched,
        twinSource,
        checkReplan: (deviations) => deviations.some((d) => Math.abs(d.delta) >= 0.1),
      }}
    >
      {children}
    </TwinContext.Provider>
  );
}
