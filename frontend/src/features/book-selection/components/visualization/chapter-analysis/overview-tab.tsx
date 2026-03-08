import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from 'recharts';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Slider } from '@/components/ui/slider';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import type { RecommendationWeights } from '../../../types';
import { cn } from '@/lib/utils';
import { useChapterAnalysis } from './context';

// ── Step display helpers ───────────────────────────────────────

const STEP_LABELS: Record<string, string> = {
  loaded_data: 'Data loaded from database',
  embedding_chapter_summaries: 'Embedding chapter summaries…',
  embedding_done: 'Embeddings generated',
  creating_book_node: 'Creating book node',
  creating_chapters: 'Creating chapter nodes',
  processing_chapter: 'Processing chapter',
  merging_similar_concepts: 'Merging similar concepts…',
  merging_done: 'Concept merging complete',
};

function stepLabel(evt: { step?: string; chapter_title?: string }): string {
  if (evt.step === 'processing_chapter' && evt.chapter_title) {
    return `Processing: ${evt.chapter_title}`;
  }
  return STEP_LABELS[evt.step ?? ''] ?? evt.step ?? '';
}

// ── Weight slider config ───────────────────────────────────────

const WEIGHT_FIELDS: {
  key: keyof RecommendationWeights;
  label: string;
  description: string;
}[] = [
  {
    key: 'coverage',
    label: 'Course Coverage',
    description: 'How much of your course this book covers',
  },
  {
    key: 'depth',
    label: 'Coverage Depth',
    description: 'How deeply it covers matched concepts',
  },
  {
    key: 'novelty',
    label: 'Novel Knowledge',
    description: 'New material beyond your course',
  },
  {
    key: 'balance',
    label: 'Topic Balance',
    description: 'Even coverage across all course topics',
  },
  {
    key: 'skillRichness',
    label: 'Skill Richness',
    description: 'Practical skills with linked concepts',
  },
  {
    key: 'density',
    label: 'Concept Density',
    description: 'Core concepts per chapter',
  },
  {
    key: 'evidenceDepth',
    label: 'Evidence Depth',
    description: 'Semantic similarity of actual text quotes (evidence embeddings)',
  },
  {
    key: 'chapterAlignment',
    label: 'Chapter Alignment',
    description: 'How well book chapters map to course lectures/documents',
  },
  {
    key: 'relevanceQuality',
    label: 'Relevance Quality',
    description: 'Proportion of matches to core vs supplementary book concepts',
  },
];

// ── Radar data helpers ─────────────────────────────────────────

const RADAR_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

function buildRadarData(
  scores: ReturnType<typeof useChapterAnalysis>['state']['scores'],
) {
  const factors: (keyof RecommendationWeights)[] = [
    'coverage',
    'depth',
    'novelty',
    'balance',
    'skillRichness',
    'density',
    'evidenceDepth',
    'chapterAlignment',
    'relevanceQuality',
  ];
  const labels = [
    'Coverage',
    'Depth',
    'Novelty',
    'Balance',
    'Skills',
    'Density',
    'Evidence',
    'Ch-Lecture',
    'Relevance',
  ];

  return labels.map((label, i) => {
    const point: Record<string, string | number> = { factor: label };
    for (const s of scores) {
      point[s.bookTitle] = Math.round(s.factors[factors[i]] * 100);
    }
    return point;
  });
}

// ── Component ──────────────────────────────────────────────────

export function OverviewTab() {
  const { state, actions } = useChapterAnalysis();
  const { scores, weights } = state;

  const selectedScore = scores.find((s) => s.bookId === state.selectedBookId) ?? null;
  const radarData = buildRadarData(scores);

  const chartConfig: ChartConfig = {};
  for (let i = 0; i < scores.length; i++) {
    chartConfig[scores[i].bookTitle] = {
      label: scores[i].bookTitle,
      color: RADAR_COLORS[i % RADAR_COLORS.length],
    };
  }

  return (
    <div className="space-y-6">
      {/* Weight Sliders */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recommendation Weights</CardTitle>
          <p className="text-sm text-muted-foreground">
            Adjust to prioritize what matters most for your course. Books
            re-rank instantly.
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {WEIGHT_FIELDS.map((field) => (
              <TooltipProvider key={field.key}>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="text-sm font-medium cursor-help">
                          {field.label}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>{field.description}</TooltipContent>
                    </Tooltip>
                    <span className="text-sm tabular-nums text-muted-foreground">
                      {(weights[field.key] * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Slider
                    min={0}
                    max={100}
                    step={5}
                    value={[weights[field.key] * 100]}
                    onValueChange={([v]) =>
                      actions.setWeights({
                        ...weights,
                        [field.key]: v / 100,
                      })
                    }
                  />
                </div>
              </TooltipProvider>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Ranked Book Cards */}
      <div className="flex gap-4 overflow-x-auto p-1 -m-1 pb-3">
        {scores.map((score, idx) => (
          <Card
            key={score.bookId}
            className={cn(
              'min-w-[220px] shrink-0 cursor-pointer transition-all',
              state.selectedBookId === score.bookId
                ? 'ring-2 ring-primary'
                : 'hover:ring-1 hover:ring-muted-foreground/30',
            )}
            onClick={() => actions.setSelectedBook(score.bookId)}
          >
            <CardContent className="pt-4 space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant={idx === 0 ? 'default' : 'secondary'}>
                  #{idx + 1}
                </Badge>
                <span className="text-xl font-bold tabular-nums">
                  {(score.composite * 100).toFixed(0)}
                </span>
              </div>
              <p className="text-sm font-medium leading-tight line-clamp-2">
                {score.bookTitle}
              </p>
              <div className="space-y-1">
                {WEIGHT_FIELDS.map((field) => (
                  <div key={field.key} className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground w-16 truncate">
                      {field.label.split(' ')[0]}
                    </span>
                    <Progress
                      value={score.factors[field.key] * 100}
                      className="h-1.5 flex-1"
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Build Curriculum Graph */}
      {scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Curriculum Knowledge Graph</CardTitle>
            <p className="text-sm text-muted-foreground">
              Transfer extracted chapters, concepts, and skills into Neo4j for
              graph-powered exploration.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {state.curriculumBuilt ? (
              <div className="rounded-lg border border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/30 p-4 space-y-3">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-green-100 dark:bg-green-900/50">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="h-4 w-4 text-green-600 dark:text-green-400"
                    >
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-green-800 dark:text-green-300">
                      Curriculum Graph Built
                    </p>
                    {selectedScore && (
                      <p className="text-sm text-green-700/80 dark:text-green-400/80">
                        {selectedScore.bookTitle}
                      </p>
                    )}
                  </div>
                </div>
                <Separator className="bg-green-200 dark:bg-green-800" />
                <p className="text-sm text-green-700 dark:text-green-400">
                  The knowledge graph is ready. Chapters, sections, concepts,
                  and skills have been transferred to Neo4j.
                </p>
              </div>
            ) : state.isBuildingCurriculum ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <svg
                    className="h-4 w-4 animate-spin text-primary"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  <span className="text-sm font-medium">Building curriculum graph…</span>
                </div>
                {state.curriculumBuildProgress.length > 0 && (
                  <div className="space-y-1 text-sm pl-6">
                    {state.curriculumBuildProgress.map((evt, i) => (
                      <div key={i} className="flex items-center gap-2">
                        {evt.event === 'error' ? (
                          <span className="text-destructive">✗</span>
                        ) : (
                          <span className="text-muted-foreground">•</span>
                        )}
                        <span
                          className={cn(
                            'text-muted-foreground',
                            evt.event === 'error' && 'text-destructive',
                          )}
                        >
                          {evt.event === 'error'
                            ? evt.message
                            : evt.event === 'progress'
                              ? stepLabel(evt)
                              : 'Complete'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button disabled={!state.selectedBookId}>
                    Build Curriculum Graph
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      Build Curriculum Graph?
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      This will construct a knowledge graph in Neo4j from the
                      selected book&apos;s chapters, sections, concepts, and
                      skills. The process embeds chapter summaries and merges
                      duplicate concepts automatically.
                      {selectedScore && (
                        <span className="block mt-2 font-medium text-foreground">
                          Book: {selectedScore.bookTitle}
                        </span>
                      )}
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction
                      onClick={() => {
                        if (state.selectedBookId) {
                          actions.buildCurriculum(state.selectedBookId);
                        }
                      }}
                    >
                      Build
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </CardContent>
        </Card>
      )}

      {/* Radar Chart */}
      {scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Factor Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="mx-auto h-[350px]">
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis dataKey="factor" tick={{ fontSize: 12 }} />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={{ fontSize: 10 }}
                />
                {scores.map((s, i) => (
                  <Radar
                    key={s.bookId}
                    name={s.bookTitle}
                    dataKey={s.bookTitle}
                    stroke={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fill={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fillOpacity={0.15}
                  />
                ))}
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
              </RadarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      )}

      {/* Score Breakdown Table */}
      {scores.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Score Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[200px]">Book</TableHead>
                  {WEIGHT_FIELDS.map((f) => (
                    <TableHead key={f.key} className="text-center">
                      {f.label.split(' ')[0]}
                    </TableHead>
                  ))}
                  <TableHead className="text-center font-semibold">
                    Composite
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {scores.map((s) => (
                  <TableRow
                    key={s.bookId}
                    className={cn(
                      state.selectedBookId === s.bookId && 'bg-muted/50',
                    )}
                  >
                    <TableCell className="font-medium max-w-[200px] truncate">
                      {s.bookTitle}
                    </TableCell>
                    {WEIGHT_FIELDS.map((f) => (
                      <TableCell key={f.key} className="text-center tabular-nums">
                        {(s.factors[f.key] * 100).toFixed(0)}
                      </TableCell>
                    ))}
                    <TableCell className="text-center font-bold tabular-nums">
                      {(s.composite * 100).toFixed(0)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
