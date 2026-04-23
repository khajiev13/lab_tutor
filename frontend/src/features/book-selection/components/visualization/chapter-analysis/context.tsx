/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { getChapterSummaries, getLatestAnalysis, openRecommendationStream, triggerChapterScoring } from '../../../api';
import { rankBooks } from '../../../lib/chapter-scoring';
import type {
  BookRecommendationScore,
  ChapterAnalysisSummary,
  RecommendationItem,
  RecommendationStreamEvent,
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

  isGeneratingRecommendations: boolean;
  recommendations: RecommendationItem[];
  recommendationSummary: string | null;
  recommendationBookTitle: string | null;
  recommendationEvents: RecommendationStreamEvent[];
  streamingText: string;
}

interface ChapterAnalysisActions {
  setSelectedBook: (bookId: number | null) => void;
  setWeights: (weights: RecommendationWeights) => void;
  setNovelThreshold: (value: number) => void;
  setCoveredThreshold: (value: number) => void;
  triggerScoring: () => Promise<void>;

  generateRecommendations: (selectedBookId: number) => void;
}

interface ChapterAnalysisMeta {
  isLoading: boolean;
  isScoring: boolean;
  error: string | null;
  hasData: boolean;
}

export interface ChapterAnalysisContextValue {
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

  const [isGeneratingRecommendations, setIsGeneratingRecommendations] = useState(false);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [recommendationSummary, setRecommendationSummary] = useState<string | null>(null);
  const [recommendationBookTitle, setRecommendationBookTitle] = useState<string | null>(null);
  const [recommendationEvents, setRecommendationEvents] = useState<RecommendationStreamEvent[]>([]);
  const [streamingText, setStreamingText] = useState('');
  const [latestRunId, setLatestRunId] = useState<number | null>(null);

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
          setLatestRunId(run.id);

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



  // Generate recommendations action
  const generateRecommendations = useCallback((bookId: number) => {
    if (!latestRunId) return;
    setIsGeneratingRecommendations(true);
    setRecommendationEvents([]);
    setRecommendations([]);
    setRecommendationSummary(null);
    setRecommendationBookTitle(null);
    setStreamingText('');
    setError(null);
    openRecommendationStream(
      courseId,
      latestRunId,
      bookId,
      (evt) => {
        if (evt.type === 'token') {
          setStreamingText((prev) => prev + evt.text);
          return;
        }
        setRecommendationEvents((prev) => [...prev, evt]);
        if (evt.type === 'report') {
          setStreamingText('');
          setRecommendations(evt.recommendations);
          setRecommendationSummary(evt.summary);
          setRecommendationBookTitle(evt.book_title);
        }
        if (evt.type === 'error' || evt.type === 'done') {
          setStreamingText('');
        }
      },
      () => setIsGeneratingRecommendations(false),
      (err) => {
        setIsGeneratingRecommendations(false);
        setError(err instanceof Error ? err.message : 'Recommendation generation failed');
      },
    );
  }, [courseId, latestRunId]);



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

        isGeneratingRecommendations,
        recommendations,
        recommendationSummary,
        recommendationBookTitle,
        recommendationEvents,
        streamingText,
      },
      actions: {
        setSelectedBook,
        setWeights,
        setNovelThreshold,
        setCoveredThreshold,
        triggerScoring: triggerScoringAction,

        generateRecommendations,
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

      isGeneratingRecommendations,
      recommendations,
      recommendationSummary,
      recommendationBookTitle,
      recommendationEvents,
      streamingText,
      isLoading,
      isScoring,
      error,
      triggerScoringAction,

      generateRecommendations,
    ],
  );

  return (
    <ChapterAnalysisContext value={value}>
      {children}
    </ChapterAnalysisContext>
  );
}
