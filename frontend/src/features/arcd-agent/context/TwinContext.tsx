/* eslint-disable react-refresh/only-export-components */
/**
 * TwinContext — provides TwinViewerData from the KG-backed backend.
 *
 * Re-fetches when `selectedUid` or `dataVersion` changes so twin data stays
 * in sync with mastery updates from review sessions.
 *
 * Production mode: API-only. No static file fallback.
 * If the backend is unreachable, twinData is null and twinError describes why.
 */
import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import type { TwinViewerData } from "@/features/arcd-agent/lib/types";

// ── API base URL (mirrors DataContext) ────────────────────────────────────

const API_BASE =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD
    ? ""
    : `http://${typeof window !== "undefined" ? window.location.hostname : "localhost"}:8000`);

// ── Context interface ──────────────────────────────────────────────────────

interface TwinContextValue {
  twinData: TwinViewerData | null;
  twinLoading: boolean;
  twinError: string | null;
  /** Always true when twinData is populated (API-only mode). */
  twinMatched: boolean;
  /** "api" when data is from the backend, null when unavailable. */
  twinSource: "api" | null;
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

// ── Provider ───────────────────────────────────────────────────────────────

interface TwinProviderProps {
  children: ReactNode;
  selectedUid: string;
  dataVersion: number;
  courseId?: string;
}

export function TwinProvider({
  children,
  selectedUid,
  dataVersion,
  courseId,
}: TwinProviderProps) {
  const [twinData, setTwinData] = useState<TwinViewerData | null>(null);
  const [twinLoading, setTwinLoading] = useState(true);
  const [twinError, setTwinError] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedUid || !courseId) {
      setTwinData(null);
      setTwinLoading(false);
      return;
    }

    let cancelled = false;
    setTwinLoading(true);
    setTwinError(null);

    async function load() {
      const token = localStorage.getItem("access_token");
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;

      try {
        const resp = await fetch(`${API_BASE}/diagnosis/arcd-twin/${courseId}`, { headers });

        if (!cancelled) {
          if (resp.status === 401) {
            setTwinError("Session expired. Please log in again.");
            setTwinData(null);
          } else if (resp.status === 503) {
            setTwinError("Knowledge Graph is not reachable.");
            setTwinData(null);
          } else if (!resp.ok) {
            setTwinError(`Failed to load twin data (HTTP ${resp.status}).`);
            setTwinData(null);
          } else {
            const data = (await resp.json()) as TwinViewerData;
            setTwinData(data.current_twin ? data : null);
            setTwinError(data.current_twin ? null : "Twin not yet computed for this student.");
          }
        }
      } catch {
        if (!cancelled) {
          setTwinError("Cannot reach the Lab Tutor backend.");
          setTwinData(null);
        }
      } finally {
        if (!cancelled) setTwinLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      setTwinLoading(false);
    };
  }, [selectedUid, dataVersion, courseId]);

  return (
    <TwinContext.Provider
      value={{
        twinData,
        twinLoading,
        twinError,
        twinMatched: twinData !== null,
        twinSource: twinData !== null ? "api" : null,
        checkReplan: (deviations) => deviations.some((d) => Math.abs(d.delta) >= 0.1),
      }}
    >
      {children}
    </TwinContext.Provider>
  );
}
