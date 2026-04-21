import { createContext, use } from 'react';
import type { ChapterAnalysisContextValue } from './context';

export const ChapterAnalysisContext =
  createContext<ChapterAnalysisContextValue | null>(null);

export function useChapterAnalysis(): ChapterAnalysisContextValue {
  const ctx = use(ChapterAnalysisContext);
  if (!ctx) {
    throw new Error(
      'useChapterAnalysis must be used within a ChapterAnalysisProvider',
    );
  }
  return ctx;
}
