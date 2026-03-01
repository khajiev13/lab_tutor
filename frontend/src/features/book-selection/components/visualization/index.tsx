import { BarChart3, Sparkles } from 'lucide-react';

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { ChapterAnalysisVisualization } from './chapter-analysis';
import { ChunkingVisualization } from './chunking-visualization';

// ── Component ──────────────────────────────────────────────────

interface BookVisualizationTabProps {
  courseId: number;
  disabled?: boolean;
}

export function BookVisualizationTab({ courseId }: BookVisualizationTabProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Book Visualization</h3>
        <p className="text-sm text-muted-foreground">
          Explore analysis results and coverage metrics for your course books.
        </p>
      </div>

      <Tabs defaultValue="chunking" className="w-full">
        <TabsList>
          <TabsTrigger value="chunking">
            <BarChart3 className="mr-2 h-4 w-4" />
            Chunking
          </TabsTrigger>
          <TabsTrigger value="extraction">
            <Sparkles className="mr-2 h-4 w-4" />
            Extraction
          </TabsTrigger>
        </TabsList>

        <TabsContent value="chunking" className="mt-6">
          <ChunkingVisualization courseId={courseId} />
        </TabsContent>

        <TabsContent value="extraction" className="mt-6">
          <ChapterAnalysisVisualization courseId={courseId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
