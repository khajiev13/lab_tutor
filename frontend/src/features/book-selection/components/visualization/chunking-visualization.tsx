import { useEffect, useState } from 'react';
import katex from 'katex';
import {
  ArrowUpDown,
  BarChart3,
  ChevronDown,
  ChevronUp,
  Gauge,
  Loader2,
  XCircle,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ReferenceLine,
  XAxis,
  YAxis,
} from 'recharts';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Slider } from '@/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { getAnalysisSummaries, getLatestAnalysis } from '../../api';
import {
  DEFAULT_COVERED_THRESHOLD,
  DEFAULT_NOVEL_THRESHOLD,
  reclassify,
  type BookAnalysisSummary,
  type ConceptCoverageItem,
  type DocumentSummaryItem,
  type ExtractionRunStatus,
} from '../../types';

// ── Constants ──────────────────────────────────────────────────

const COMPLETED_STATUSES: ExtractionRunStatus[] = [
  'completed',
  'book_picked',
  'agentic_extracting',
  'agentic_completed',
];

// ── Types ──────────────────────────────────────────────────────

type TieredConcept = ConceptCoverageItem & {
  tier: 'novel' | 'overlap' | 'covered';
};

// ── Chart configs ──────────────────────────────────────────────

const GAP_CHART_CONFIG = {
  covered: { label: 'Covered', color: 'var(--chart-2)' },
  overlap: { label: 'Partial', color: 'var(--chart-4)' },
  novel: { label: 'Gap', color: 'var(--chart-5)' },
} satisfies ChartConfig;

const RADAR_CHART_CONFIG = {
  score: { label: 'Topic score', color: 'var(--chart-1)' },
  score2: { label: 'Topic score 2', color: 'var(--chart-2)' },
} satisfies ChartConfig;

const DISTRIBUTION_CHART_CONFIG = {
  count: { label: 'Concepts', color: 'var(--chart-1)' },
} satisfies ChartConfig;

// ── Helpers ────────────────────────────────────────────────────

function getTierBadgeVariant(tier: TieredConcept['tier']) {
  if (tier === 'covered') return 'default';
  if (tier === 'overlap') return 'secondary';
  return 'destructive';
}

function getTierLabel(tier: TieredConcept['tier']) {
  if (tier === 'covered') return 'Covered';
  if (tier === 'overlap') return 'Partial';
  return 'Gap';
}

function clampThresholds(novel: number, covered: number): [number, number] {
  const low = Math.max(0, Math.min(novel, 0.95));
  const high = Math.max(0.05, Math.min(covered, 1));
  if (high <= low + 0.01) {
    return [low, Math.min(1, low + 0.01)];
  }
  return [low, high];
}

function bucketLabelForThreshold(threshold: number) {
  const start = Math.floor(threshold / 0.05) * 0.05;
  return `${start.toFixed(2)}-${(start + 0.05).toFixed(2)}`;
}

function KatexFormula({ formula, block = false }: { formula: string; block?: boolean }) {
  const html = katex.renderToString(formula, { throwOnError: false, displayMode: block });
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

function buildGapRows(
  summaries: BookAnalysisSummary[],
  novelThr: number,
  coveredThr: number,
) {
  return summaries.map((summary) => {
    const tiered = reclassify(summary.course_coverage, novelThr, coveredThr);
    const covered = tiered.filter((item) => item.tier === 'covered').length;
    const overlap = tiered.filter((item) => item.tier === 'overlap').length;
    const novel = tiered.filter((item) => item.tier === 'novel').length;
    return { bookTitle: summary.book_title, covered, overlap, novel, total: tiered.length };
  });
}

function buildRadarRows(summaries: BookAnalysisSummary[]) {
  const topics = new Set<string>();
  summaries.forEach((summary) => {
    Object.keys(summary.topic_scores).forEach((topic) => topics.add(topic));
  });
  return Array.from(topics)
    .sort()
    .map((topic) => {
      const row: Record<string, number | string> = { topic };
      summaries.forEach((summary, idx) => {
        row[`score-${idx}`] = summary.topic_scores[topic] ?? 0;
      });
      return row;
    });
}

// ── Sub-components ─────────────────────────────────────────────

function DocumentSummariesCard({ items }: { items: DocumentSummaryItem[] }) {
  const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

  const tierFor = (score: number) =>
    score >= DEFAULT_COVERED_THRESHOLD
      ? 'covered'
      : score >= DEFAULT_NOVEL_THRESHOLD
        ? 'overlap'
        : 'novel';

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="text-sm">Document Summaries</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[300px]">Topic</TableHead>
              <TableHead className="text-right">Similarity</TableHead>
              <TableHead>Tier</TableHead>
              <TableHead className="w-[80px] text-right">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((doc) => {
              const tier = tierFor(doc.sim_score);
              const isExpanded = expandedDoc === doc.document_id;
              return (
                <>
                  <TableRow key={doc.document_id}>
                    <TableCell className="font-medium">
                      {doc.topic ?? doc.document_id}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {doc.sim_score.toFixed(3)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={getTierBadgeVariant(tier)}>
                        {getTierLabel(tier)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setExpandedDoc((prev) =>
                            prev === doc.document_id ? null : doc.document_id,
                          )
                        }
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                  {isExpanded && (
                    <TableRow>
                      <TableCell colSpan={4} className="whitespace-normal">
                        <div className="rounded-md border bg-muted/20 p-3 text-sm leading-6">
                          {doc.summary_text || 'No summary text available.'}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ── Component ──────────────────────────────────────────────────

interface ChunkingVisualizationProps {
  courseId: number;
}

export function ChunkingVisualization({ courseId }: ChunkingVisualizationProps) {
  const [summaries, setSummaries] = useState<BookAnalysisSummary[]>([]);
  const [selectedSummaryId, setSelectedSummaryId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [novelThreshold, setNovelThreshold] = useState(DEFAULT_NOVEL_THRESHOLD);
  const [coveredThreshold, setCoveredThreshold] = useState(DEFAULT_COVERED_THRESHOLD);
  const [tierFilter, setTierFilter] = useState<'all' | TieredConcept['tier']>('all');
  const [isSortDesc, setIsSortDesc] = useState(true);
  const [expandedConcept, setExpandedConcept] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const run = await getLatestAnalysis(courseId);
        if (cancelled) return;
        if (!run || !COMPLETED_STATUSES.includes(run.status)) {
          setIsLoading(false);
          return;
        }
        const data = await getAnalysisSummaries(courseId, run.id);
        if (cancelled) return;
        setSummaries(data);
        setSelectedSummaryId(data[0]?.id ?? null);
      } catch {
        if (!cancelled) setError('Failed to load analysis summaries.');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [courseId]);

  // ── Derived state ────────────────────────────────────────────

  const [safeNovelThreshold, safeCoveredThreshold] = clampThresholds(
    novelThreshold,
    coveredThreshold,
  );
  const gapRows = buildGapRows(summaries, safeNovelThreshold, safeCoveredThreshold);
  const selectedSummary =
    summaries.find((s) => s.id === selectedSummaryId) ?? summaries[0] ?? null;
  const tieredCoverage: TieredConcept[] = selectedSummary
    ? reclassify(selectedSummary.course_coverage, safeNovelThreshold, safeCoveredThreshold)
    : [];
  const filteredCoverage = tieredCoverage
    .filter((item) => tierFilter === 'all' || item.tier === tierFilter)
    .sort((a, b) => (isSortDesc ? b.sim_max - a.sim_max : a.sim_max - b.sim_max));
  const radarRows = buildRadarRows(summaries);
  const distributionRows = (selectedSummary?.sim_distribution ?? []).map((bucket) => {
    const mid = (bucket.bucket_start + bucket.bucket_end) / 2;
    const tier =
      mid < safeNovelThreshold
        ? 'novel'
        : mid < safeCoveredThreshold
          ? 'overlap'
          : 'covered';
    return {
      bucketLabel: `${bucket.bucket_start.toFixed(2)}-${bucket.bucket_end.toFixed(2)}`,
      count: bucket.count,
      tier,
    };
  });

  // ── Render ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <XCircle className="h-4 w-4" />
        <AlertTitle>Could not load summaries</AlertTitle>
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    );
  }

  if (summaries.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center justify-center py-16 text-center">
          <BarChart3 className="mb-4 h-12 w-12 text-muted-foreground/40" />
          <p className="text-muted-foreground">
            No chunking analysis results available yet.
            <br />
            Run the chunking pipeline in the <strong>Book Analysis</strong> tab first.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h4 className="text-base font-semibold">Concept Alignment Dashboard</h4>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Gauge className="h-4 w-4" />
          <span>
            Novel &lt; {safeNovelThreshold.toFixed(2)} · Covered ≥{' '}
            {safeCoveredThreshold.toFixed(2)}
          </span>
        </div>
      </div>

      {/* Thresholds */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Thresholds</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Slider
            value={[safeNovelThreshold, safeCoveredThreshold]}
            min={0}
            max={1}
            step={0.01}
            onValueChange={(value) => {
              if (value.length < 2) return;
              const [novel, covered] = clampThresholds(value[0], value[1]);
              setNovelThreshold(novel);
              setCoveredThreshold(covered);
            }}
          />
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Novel threshold: {safeNovelThreshold.toFixed(2)}</span>
            <span>Covered threshold: {safeCoveredThreshold.toFixed(2)}</span>
          </div>
        </CardContent>
      </Card>

      {/* Coverage Breakdown */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Coverage Breakdown</CardTitle>
          <CardDescription className="text-xs leading-relaxed">
            Shows how many of the book's concepts map to your course syllabus.
            <span className="ml-1 font-medium text-green-600 dark:text-green-400">Covered</span> — strong match;
            <span className="mx-1 font-medium text-yellow-600 dark:text-yellow-400">Partial</span> — related but loose;
            <span className="ml-1 font-medium text-red-500">Gap</span> — new content not in the curriculum.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer
            config={GAP_CHART_CONFIG}
            className="h-[260px] w-full"
          >
            <BarChart data={gapRows} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" allowDecimals={false} />
              <YAxis
                type="category"
                width={140}
                dataKey="bookTitle"
                tickLine={false}
                axisLine={false}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="covered" stackId="a" fill="var(--color-covered)">
                <LabelList dataKey="covered" position="inside" style={{ fill: '#fff', fontSize: 11, fontWeight: 600 }} formatter={(v: number) => v > 0 ? v : ''} />
              </Bar>
              <Bar dataKey="overlap" stackId="a" fill="var(--color-overlap)">
                <LabelList dataKey="overlap" position="inside" style={{ fill: '#fff', fontSize: 11, fontWeight: 600 }} formatter={(v: number) => v > 0 ? v : ''} />
              </Bar>
              <Bar dataKey="novel" stackId="a" fill="var(--color-novel)" radius={[0, 4, 4, 0]}>
                <LabelList dataKey="novel" position="inside" style={{ fill: '#fff', fontSize: 11, fontWeight: 600 }} formatter={(v: number) => v > 0 ? v : ''} />
              </Bar>
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      {/* Book Focus */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Book Focus</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs
            value={String(selectedSummary?.id ?? '')}
            onValueChange={(value) => setSelectedSummaryId(Number(value))}
          >
            <TabsList>
              {summaries.map((summary) => (
                <TabsTrigger key={summary.id} value={String(summary.id)}>
                  {summary.book_title}
                </TabsTrigger>
              ))}
            </TabsList>
            {summaries.map((summary) => (
              <TabsContent key={summary.id} value={String(summary.id)} className="pt-4">
                <div className="grid gap-4 lg:grid-cols-2">
                  {/* Topic Radar */}
                  <Card className="lg:col-span-2">
                    <CardHeader>
                      <CardTitle className="text-sm">Topic Radar</CardTitle>
                      <CardDescription className="text-xs leading-relaxed space-y-1">
                        <span className="block">Each axis is a course topic. Its score is the average best-match similarity of all concepts in that topic against the book&apos;s chunks:</span>
                        <span className="block py-1">
                          <KatexFormula block formula="\text{score}(t) = \frac{1}{|C_t|} \sum_{c \,\in\, C_t} \max_{k}\, \cos(\vec{c},\, \vec{k})" />
                        </span>
                        <span className="block">where <KatexFormula formula="C_t" /> = concepts in topic <KatexFormula formula="t" />, <KatexFormula formula="\vec{c}" /> = concept embedding, <KatexFormula formula="\vec{k}" /> = book chunk embedding. Score closer to 1.0 means better coverage.</span>
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ChartContainer
                        config={RADAR_CHART_CONFIG}
                        className="h-[420px] w-full"
                      >
                        <RadarChart
                          data={radarRows}
                          outerRadius="100%"
                          margin={{ top: 20, right: 80, bottom: 20, left: 80 }}
                        >
                          <PolarGrid />
                          <PolarRadiusAxis
                            angle={30}
                            domain={[0, 1]}
                            tickCount={4}
                            tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }}
                            tickFormatter={(v: number) => v.toFixed(1)}
                          />
                          <PolarAngleAxis
                            dataKey="topic"
                            tickFormatter={(value: string) => {
                              const maxLen = 26;
                              const str = value ?? '';
                              return str.length > maxLen ? str.slice(0, maxLen - 1) + '…' : str;
                            }}
                            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                          />
                          {summaries.map((item, idx) => (
                            <Radar
                              key={item.id}
                              dataKey={`score-${idx}`}
                              name={item.book_title}
                              stroke={
                                idx === 0
                                  ? 'var(--color-score)'
                                  : 'var(--color-score2)'
                              }
                              fill={
                                idx === 0
                                  ? 'var(--color-score)'
                                  : 'var(--color-score2)'
                              }
                              fillOpacity={0.2}
                            />
                          ))}
                          <ChartTooltip content={<ChartTooltipContent />} />
                          <ChartLegend content={<ChartLegendContent />} />
                        </RadarChart>
                      </ChartContainer>
                    </CardContent>
                  </Card>

                  {/* Similarity Distribution */}
                  <Card className="lg:col-span-2">
                    <CardHeader>
                      <CardTitle className="text-sm">Similarity Distribution</CardTitle>
                      <CardDescription className="text-xs leading-relaxed">
                        Distribution of <KatexFormula formula="\text{sim\_max}(c) = \max_k\,\cos(\vec{c}, \vec{k})" /> values across all course concepts.
                        The dashed lines mark the Novel / Covered thresholds set above.
                      </CardDescription>
                    </CardHeader>
                    <CardContent>
                      <ChartContainer
                        config={DISTRIBUTION_CHART_CONFIG}
                        className="h-[280px] w-full"
                      >
                        <BarChart data={distributionRows}>
                          <CartesianGrid vertical={false} />
                          <XAxis
                            dataKey="bucketLabel"
                            tickLine={false}
                            axisLine={false}
                            interval={1}
                            tickMargin={8}
                            angle={-45}
                            textAnchor="end"
                            height={60}
                          />
                          <YAxis allowDecimals={false} />
                          <ChartTooltip content={<ChartTooltipContent />} />
                          <ReferenceLine
                            x={bucketLabelForThreshold(safeNovelThreshold)}
                            strokeDasharray="3 3"
                          />
                          <ReferenceLine
                            x={bucketLabelForThreshold(safeCoveredThreshold)}
                            strokeDasharray="3 3"
                          />
                          <Bar dataKey="count" radius={4}>
                            {distributionRows.map((entry) => (
                              <Cell
                                key={entry.bucketLabel}
                                style={{
                                  fill:
                                    entry.tier === 'covered'
                                      ? 'var(--chart-2)'
                                      : entry.tier === 'overlap'
                                        ? 'var(--chart-4)'
                                        : 'var(--chart-5)',
                                }}
                              />
                            ))}
                          </Bar>
                        </BarChart>
                      </ChartContainer>
                    </CardContent>
                  </Card>
                </div>

                {/* Document Summaries */}
                {summary.document_summaries?.length > 0 && (
                  <DocumentSummariesCard items={summary.document_summaries} />
                )}
              </TabsContent>
            ))}
          </Tabs>
        </CardContent>
      </Card>

      {/* Concept Coverage table */}
      {selectedSummary && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="text-sm">
              Concept Coverage · {selectedSummary.book_title}
            </CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsSortDesc((prev) => !prev)}
            >
              <ArrowUpDown className="mr-1 h-4 w-4" />
              {isSortDesc ? 'High → Low' : 'Low → High'}
            </Button>
          </CardHeader>
          <CardContent className="space-y-3">
            <Tabs
              value={tierFilter}
              onValueChange={(value) =>
                setTierFilter(value as 'all' | TieredConcept['tier'])
              }
            >
              <TabsList>
                <TabsTrigger value="all">All</TabsTrigger>
                <TabsTrigger value="covered">Covered</TabsTrigger>
                <TabsTrigger value="overlap">Partial</TabsTrigger>
                <TabsTrigger value="novel">Gaps</TabsTrigger>
              </TabsList>
            </Tabs>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[260px]">Concept</TableHead>
                  <TableHead>Topic</TableHead>
                  <TableHead className="text-right">Similarity</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead className="w-[120px] text-right">Evidence</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredCoverage.map((item) => {
                  const isExpanded = expandedConcept === item.concept_name;
                  return (
                    <>
                      <TableRow key={item.concept_name}>
                        <TableCell className="font-medium">
                          {item.concept_name}
                        </TableCell>
                        <TableCell>{item.doc_topic ?? '—'}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {item.sim_max.toFixed(3)}
                        </TableCell>
                        <TableCell>
                          <Badge variant={getTierBadgeVariant(item.tier)}>
                            {getTierLabel(item.tier)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              setExpandedConcept((prev) =>
                                prev === item.concept_name
                                  ? null
                                  : item.concept_name,
                              )
                            }
                          >
                            {isExpanded ? (
                              <ChevronUp className="h-4 w-4" />
                            ) : (
                              <ChevronDown className="h-4 w-4" />
                            )}
                          </Button>
                        </TableCell>
                      </TableRow>
                      {isExpanded && (
                        <TableRow>
                          <TableCell colSpan={5} className="whitespace-normal">
                            <div className="rounded-md border bg-muted/20 p-3 text-sm leading-6">
                              {item.best_match || 'No evidence snippet available.'}
                            </div>
                          </TableCell>
                        </TableRow>
                      )}
                    </>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
