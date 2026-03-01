import {
  BarChart3,
  BookOpen,
  GitCompare,
  Layers,
  Lightbulb,
  Target,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { ChapterAnalysisProvider, useChapterAnalysis } from './context';
import { ChaptersTab } from './chapters-tab';
import { CompareTab } from './compare-tab';
import { CoverageTab } from './coverage-tab';
import { NoveltyTab } from './novelty-tab';
import { OverviewTab } from './overview-tab';
import { TopicsTab } from './topics-tab';

// ── Orchestrator ───────────────────────────────────────────────

interface ChapterAnalysisVisualizationProps {
  courseId: number;
}

export function ChapterAnalysisVisualization({
  courseId,
}: ChapterAnalysisVisualizationProps) {
  return (
    <ChapterAnalysisProvider courseId={courseId}>
      <ChapterAnalysisContent />
    </ChapterAnalysisProvider>
  );
}

// ── Inner content (has access to context) ──────────────────────

function ChapterAnalysisContent() {
  const { meta, actions } = useChapterAnalysis();

  if (meta.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-[200px] w-full" />
        <Skeleton className="h-[200px] w-full" />
      </div>
    );
  }

  if (!meta.hasData) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center space-y-4">
        <Target className="h-12 w-12 text-muted-foreground/40" />
        <p className="text-muted-foreground">
          No chapter analysis data yet.
          <br />
          Run scoring to analyse how each book covers your course concepts.
        </p>
        <Button onClick={actions.triggerScoring} disabled={meta.isScoring}>
          {meta.isScoring ? 'Scoring…' : 'Run Chapter Scoring'}
        </Button>
        {meta.error && (
          <p className="text-sm text-destructive">{meta.error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {meta.error && (
        <p className="text-sm text-destructive">{meta.error}</p>
      )}

      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="flex-wrap h-auto gap-1">
          <TabsTrigger value="overview">
            <BarChart3 className="mr-1.5 h-3.5 w-3.5" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="coverage">
            <Target className="mr-1.5 h-3.5 w-3.5" />
            Coverage
          </TabsTrigger>
          <TabsTrigger value="novelty">
            <Lightbulb className="mr-1.5 h-3.5 w-3.5" />
            Novelty
          </TabsTrigger>
          <TabsTrigger value="topics">
            <Layers className="mr-1.5 h-3.5 w-3.5" />
            Topics
          </TabsTrigger>
          <TabsTrigger value="chapters">
            <BookOpen className="mr-1.5 h-3.5 w-3.5" />
            Chapters
          </TabsTrigger>
          <TabsTrigger value="compare">
            <GitCompare className="mr-1.5 h-3.5 w-3.5" />
            Compare
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="mt-4">
          <OverviewTab />
        </TabsContent>
        <TabsContent value="coverage" className="mt-4">
          <CoverageTab />
        </TabsContent>
        <TabsContent value="novelty" className="mt-4">
          <NoveltyTab />
        </TabsContent>
        <TabsContent value="topics" className="mt-4">
          <TopicsTab />
        </TabsContent>
        <TabsContent value="chapters" className="mt-4">
          <ChaptersTab />
        </TabsContent>
        <TabsContent value="compare" className="mt-4">
          <CompareTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
