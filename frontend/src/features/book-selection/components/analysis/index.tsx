import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BarChart3,
  Bot,
  CheckCircle2,
  Cpu,
  FileText,
  Layers,
  Loader2,
  Play,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import {
  getLatestAnalysis,
  openEmbeddingProgressStream,
  triggerAnalysis,
} from '../../api';
import { AgenticAnalysis } from './agentic-analysis';
import {
  type EmbeddingBookProgress,
  type ExtractionRunStatus,
  type BookExtractionRun,
} from '../../types';

// ── Constants ──────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3_000;

const ACTIVE_STATUSES: ExtractionRunStatus[] = [
  'pending',
  'extracting',
  'chapter_extracted',
  'chunking',
  'embedding',
  'scoring',
  'agentic_extracting',
];

// ── Status helpers ─────────────────────────────────────────────

interface StepConfig {
  label: string;
  icon: React.ElementType;
  activeStatuses: ExtractionRunStatus[];
}

const STEPS: StepConfig[] = [
  {
    label: 'Extract PDFs',
    icon: FileText,
    activeStatuses: ['extracting', 'chapter_extracted'],
  },
  {
    label: 'Chunk paragraphs',
    icon: Layers,
    activeStatuses: ['chunking'],
  },
  {
    label: 'Embed chunks',
    icon: Cpu,
    activeStatuses: ['embedding'],
  },
  {
    label: 'Score concepts',
    icon: BarChart3,
    activeStatuses: ['scoring'],
  },
];

function stepState(
  stepIndex: number,
  runStatus: ExtractionRunStatus,
): 'pending' | 'active' | 'done' {
  const statusOrder: ExtractionRunStatus[] = [
    'pending',
    'extracting',
    'chapter_extracted',
    'chunking',
    'embedding',
    'scoring',
    'completed',
    'book_picked',
    'agentic_extracting',
    'agentic_completed',
  ];
  const currentIdx = statusOrder.indexOf(runStatus);
  // Map step index to the status index that *follows* completion of that step
  // Step 0 (extract) is done when status >= chunking (idx 3)
  // Step 1 (chunk)   is done when status >= embedding (idx 4)
  // Step 2 (embed)   is done when status >= scoring (idx 5)
  // Step 3 (score)   is done when status >= completed (idx 6)
  const doneAfter = [3, 4, 5, 6];
  // Which status indices mark a step as "active"
  const activeIndices: number[][] = [[1, 2], [3], [4], [5]];

  if (currentIdx >= doneAfter[stepIndex]) return 'done';
  if (activeIndices[stepIndex].includes(currentIdx)) return 'active';
  return 'pending';
}

function parseProgress(detail: string | null): number | null {
  if (!detail) return null;
  const m = detail.match(/(\d+)%/);
  return m ? Number(m[1]) : null;
}

function statusBadge(status: ExtractionRunStatus) {
  const map: Record<
    ExtractionRunStatus,
    { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }
  > = {
    pending: { label: 'Queued', variant: 'secondary' },
    extracting: { label: 'Extracting', variant: 'default' },
    chapter_extracted: { label: 'Chapters Ready', variant: 'default' },
    chunking: { label: 'Chunking', variant: 'default' },
    embedding: { label: 'Embedding', variant: 'default' },
    scoring: { label: 'Scoring', variant: 'default' },
    completed: { label: 'Completed', variant: 'outline' },
    failed: { label: 'Failed', variant: 'destructive' },
    book_picked: { label: 'Book picked', variant: 'outline' },
    agentic_extracting: { label: 'Agentic Extraction', variant: 'default' },
    agentic_completed: { label: 'Agentic Done', variant: 'outline' },
  };
  return map[status] ?? { label: status, variant: 'secondary' as const };
}

// ── Component ──────────────────────────────────────────────────

interface BookAnalysisTabProps {
  courseId: number;
  disabled?: boolean;
}

export function BookAnalysisTab({ courseId, disabled }: BookAnalysisTabProps) {
  const [run, setRun] = useState<BookExtractionRun | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [embeddingProgress, setEmbeddingProgress] = useState<EmbeddingBookProgress[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const sseRef = useRef<AbortController | null>(null);

  // ── Polling ────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (cId: number) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const latest = await getLatestAnalysis(cId);
          if (!latest) return;
          setRun(latest);
          if (!ACTIVE_STATUSES.includes(latest.status)) {
            stopPolling();
          }
        } catch {
          // Swallow transient poll errors
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  // ── SSE embedding progress ──────────────────────────────

  useEffect(() => {
    if (run?.status !== 'embedding') {
      sseRef.current?.abort();
      sseRef.current = null;
      setEmbeddingProgress([]);
      return;
    }
    if (sseRef.current) return; // already connected
    sseRef.current = openEmbeddingProgressStream(
      courseId,
      run.id,
      (event) => setEmbeddingProgress(event.books),
      () => { sseRef.current = null; },
    );
    return () => {
      sseRef.current?.abort();
      sseRef.current = null;
    };
  }, [courseId, run?.id, run?.status]);

  // ── Initial load ───────────────────────────────────────────

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const latest = await getLatestAnalysis(courseId);
        if (cancelled) return;
        setRun(latest);
        if (latest && ACTIVE_STATUSES.includes(latest.status)) {
          startPolling(courseId);
        }
      } catch {
        if (!cancelled) setError('Failed to load analysis status.');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [courseId, startPolling]);

  // ── Trigger ────────────────────────────────────────────────

  const handleStart = async () => {
    setIsSubmitting(true);
    setError(null);
    try {
      const newRun = await triggerAnalysis(courseId);
      setRun(newRun);
      startPolling(courseId);
      toast.success('Chunking analysis started');
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to start analysis';
      setError(msg);
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // ── Derived state ──────────────────────────────────────────

  const isActive = run ? ACTIVE_STATUSES.includes(run.status) : false;
  const pct = run ? parseProgress(run.progress_detail) : null;
  const badge = run ? statusBadge(run.status) : null;

  const canShowAgentic = run && ['completed', 'book_picked', 'agentic_extracting', 'agentic_completed'].includes(run.status);

  // ── Render ─────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Book Analysis</h3>
          <p className="text-sm text-muted-foreground">
            Run analysis pipelines on your selected books. View results in the
            Visualization tab.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {badge && <Badge variant={badge.variant}>{badge.label}</Badge>}
          <Button
            onClick={handleStart}
            disabled={disabled || isSubmitting || isActive}
          >
            {isSubmitting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            {run ? 'Re-run analysis' : 'Start analysis'}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Run failed */}
      {run?.status === 'failed' && run.error_message && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Analysis failed</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">
            {run.error_message}
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="chunking" className="w-full">
        <TabsList>
          <TabsTrigger value="chunking">
            <Layers className="mr-2 h-4 w-4" />
            Chunking
          </TabsTrigger>
          <TabsTrigger value="agentic">
            <Bot className="mr-2 h-4 w-4" />
            Agentic Extraction
          </TabsTrigger>
        </TabsList>

        <TabsContent value="chunking" className="mt-6 space-y-6">
          {/* Progress card — shown when there's an active or completed run */}
          {run && (
            <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Pipeline progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Step indicators */}
            <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {STEPS.map((step, i) => {
                const state = stepState(i, run.status);
                const Icon = step.icon;
                return (
                  <div
                    key={step.label}
                    className={`flex flex-col items-center gap-2 rounded-lg border p-4 transition-colors ${
                      state === 'active'
                        ? 'border-primary bg-primary/5'
                        : state === 'done'
                          ? 'border-green-500/40 bg-green-50 dark:bg-green-950/20'
                          : 'border-muted'
                    }`}
                  >
                    {state === 'done' ? (
                      <CheckCircle2 className="h-6 w-6 text-green-600" />
                    ) : state === 'active' ? (
                      <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    ) : (
                      <Icon className="h-6 w-6 text-muted-foreground" />
                    )}
                    <span
                      className={`text-sm font-medium ${
                        state === 'active'
                          ? 'text-primary'
                          : state === 'done'
                            ? 'text-green-700 dark:text-green-400'
                            : 'text-muted-foreground'
                      }`}
                    >
                      {step.label}
                    </span>
                  </div>
                );
              })}
            </div>

            {/* Progress bar */}
            {isActive && pct !== null && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">
                    {run.progress_detail}
                  </span>
                  <span className="tabular-nums font-medium">{pct}%</span>
                </div>
                <Progress value={pct} className="h-2" />
              </div>
            )}

            {/* Queued / non-percentage detail */}
            {isActive && pct === null && run.progress_detail && (
              <p className="text-sm text-muted-foreground">
                {run.progress_detail}
              </p>
            )}

            {/* Per-book embedding progress — shown when books are being embedded */}
            {run.status === 'embedding' && (
              <div className="space-y-3">
                <p className="text-sm font-medium text-muted-foreground">Embedding progress by book</p>
                {embeddingProgress.length === 0 && (
                  <p className="text-xs text-muted-foreground animate-pulse">
                    Connecting to progress stream…
                  </p>
                )}
                {embeddingProgress.map((book) => {
                  const pct = book.total_chunks > 0
                    ? Math.round((book.embedded_chunks / book.total_chunks) * 100)
                    : 0;
                  return (
                    <div key={book.selected_book_id} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="truncate max-w-[70%] text-muted-foreground">
                          {book.title}
                        </span>
                        <span className="tabular-nums text-xs font-medium">
                          {book.embedded_chunks} / {book.total_chunks} chunks ({pct}%)
                        </span>
                      </div>
                      <Progress value={pct} className="h-1.5" />
                    </div>
                  );
                })}
              </div>
            )}

            {/* Completed summary */}
            {['completed', 'book_picked', 'agentic_extracting', 'agentic_completed'].includes(run.status) && (
              <div className="flex items-center gap-2 text-sm text-green-700 dark:text-green-400">
                <CheckCircle2 className="h-4 w-4" />
                <span>{run.progress_detail ?? 'Analysis complete'}</span>
              </div>
            )}

            {/* Timestamps */}
            <p className="text-xs text-muted-foreground">
              Started{' '}
              {new Date(run.created_at).toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
              })}
              {run.embedding_model && (
                <>
                  {' · '}
                  Model: {run.embedding_model} ({run.embedding_dims}d)
                </>
              )}
            </p>
          </CardContent>
        </Card>
      )}

          {/* Empty state */}
          {!run && !error && (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <Cpu className="mb-4 h-12 w-12 text-muted-foreground/40" />
                <p className="text-muted-foreground">
                  No analysis has been run for this course yet.
                  <br />
                  Click <strong>Start analysis</strong> to extract, chunk, and embed
                  book content.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="agentic" className="mt-6 space-y-6">
          {canShowAgentic ? (
            <Card>
              <CardContent className="pt-6">
                <AgenticAnalysis
                  courseId={courseId}
                  runId={run!.id}
                  runStatus={run!.status}
                  onStatusChange={(newStatus) =>
                    setRun((prev) => (prev ? { ...prev, status: newStatus } : prev))
                  }
                />
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                <Bot className="mb-4 h-12 w-12 text-muted-foreground/40" />
                <p className="text-muted-foreground">
                  Complete the chunking pipeline first to enable agentic
                  extraction.
                  <br />
                  Switch to the <strong>Chunking</strong> tab and run the
                  analysis.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
