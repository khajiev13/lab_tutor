import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { getChapterSummaries, getLatestAnalysis, triggerChapterScoring } from '../../../api';
import { rankBooks } from '../../../lib/chapter-scoring';
import type {
  BookRecommendationScore,
  ChapterAnalysisSummary,
  RecommendationWeights,
} from '../../../types';
import {
  DEFAULT_COVERED_THRESHOLD,
  DEFAULT_NOVEL_THRESHOLD,
  DEFAULT_RECOMMENDATION_WEIGHTS,
} from '../../../types';

// ── Context Interface ──────────────────────────────────────────

interface ChapterAnalysisState {
  summaries: ChapterAnalysisSummary[];
  scores: BookRecommendationScore[];
  selectedBookId: number | null;
  weights: RecommendationWeights;
  novelThreshold: number;
  coveredThreshold: number;
}

interface ChapterAnalysisActions {
  setSelectedBook: (bookId: number | null) => void;
  setWeights: (weights: RecommendationWeights) => void;
  setNovelThreshold: (value: number) => void;
  setCoveredThreshold: (value: number) => void;
  triggerScoring: () => Promise<void>;
}

interface ChapterAnalysisMeta {
  isLoading: boolean;
  isScoring: boolean;
  error: string | null;
  hasData: boolean;
}

interface ChapterAnalysisContextValue {
  state: ChapterAnalysisState;
  actions: ChapterAnalysisActions;
  meta: ChapterAnalysisMeta;
}

export const ChapterAnalysisContext =
  createContext<ChapterAnalysisContextValue | null>(null);

// ── Hook ───────────────────────────────────────────────────────

export function useChapterAnalysis(): ChapterAnalysisContextValue {
  const ctx = use(ChapterAnalysisContext);
  if (!ctx) {
    throw new Error(
      'useChapterAnalysis must be used within a ChapterAnalysisProvider',
    );
  }
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────

interface ChapterAnalysisProviderProps {
  courseId: number;
  children: React.ReactNode;
}

export function ChapterAnalysisProvider({
  courseId,
  children,
}: ChapterAnalysisProviderProps) {
  const [summaries, setSummaries] = useState<ChapterAnalysisSummary[]>([]);
  const [selectedBookId, setSelectedBook] = useState<number | null>(null);
  const [weights, setWeights] = useState<RecommendationWeights>(
    DEFAULT_RECOMMENDATION_WEIGHTS,
  );
  const [novelThreshold, setNovelThreshold] = useState(DEFAULT_NOVEL_THRESHOLD);
  const [coveredThreshold, setCoveredThreshold] = useState(
    DEFAULT_COVERED_THRESHOLD,
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isScoring, setIsScoring] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch existing summaries on mount
  useEffect(() => {
    let cancelled = false;

    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const run = await getLatestAnalysis(courseId);
        if (!run || cancelled) {
          setIsLoading(false);
          return;
        }
        const data = await getChapterSummaries(courseId, run.id);
        if (!cancelled) {
          setSummaries(data);
          if (data.length > 0) setSelectedBook(data[0].selected_book_id);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load chapter analysis');
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [courseId]);

  // Trigger scoring (POST)
  const triggerScoringAction = useCallback(async () => {
    setIsScoring(true);
    setError(null);
    try {
      const run = await getLatestAnalysis(courseId);
      if (!run) throw new Error('No analysis run found');
      const data = await triggerChapterScoring(courseId, run.id);
      setSummaries(data);
      if (data.length > 0 && !selectedBookId) {
        setSelectedBook(data[0].selected_book_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scoring failed');
    } finally {
      setIsScoring(false);
    }
  }, [courseId, selectedBookId]);

  // Recompute scores whenever summaries, weights, or thresholds change
  const scores = useMemo(
    () => rankBooks(summaries, weights, coveredThreshold, novelThreshold),
    [summaries, weights, coveredThreshold, novelThreshold],
  );

  const value = useMemo<ChapterAnalysisContextValue>(
    () => ({
      state: {
        summaries,
        scores,
        selectedBookId,
        weights,
        novelThreshold,
        coveredThreshold,
      },
      actions: {
        setSelectedBook,
        setWeights,
        setNovelThreshold,
        setCoveredThreshold,
        triggerScoring: triggerScoringAction,
      },
      meta: {
        isLoading,
        isScoring,
        error,
        hasData: summaries.length > 0,
      },
    }),
    [
      summaries,
      scores,
      selectedBookId,
      weights,
      novelThreshold,
      coveredThreshold,
      isLoading,
      isScoring,
      error,
      triggerScoringAction,
    ],
  );

  return (
    <ChapterAnalysisContext value={value}>
      {children}
    </ChapterAnalysisContext>
  );
}
