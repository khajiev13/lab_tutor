import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FileText,
  Layers,
  Cpu,
  CheckCircle2,
  XCircle,
  Play,
  Loader2,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

import { triggerAnalysis, getLatestAnalysis } from '../../api';
import type { BookExtractionRun, ExtractionRunStatus } from '../../types';

// ── Constants ──────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3_000;

const ACTIVE_STATUSES: ExtractionRunStatus[] = [
  'pending',
  'extracting',
  'embedding',
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
    activeStatuses: ['extracting'],
  },
  {
    label: 'Chunk paragraphs',
    icon: Layers,
    activeStatuses: [], // shown as done when embedding starts
  },
  {
    label: 'Embed chunks',
    icon: Cpu,
    activeStatuses: ['embedding'],
  },
];

function stepState(
  stepIndex: number,
  runStatus: ExtractionRunStatus,
): 'pending' | 'active' | 'done' {
  const statusOrder: ExtractionRunStatus[] = [
    'pending',
    'extracting',
    'embedding',
    'completed',
    'book_picked',
  ];
  const currentIdx = statusOrder.indexOf(runStatus);
  // Map step index to the status index that *follows* completion of that step
  // Step 0 (extract) is done when status >= embedding (idx 2)
  // Step 1 (chunk)   is done when status >= embedding (idx 2)   (runs inside extract→chunk edge)
  // Step 2 (embed)   is done when status >= completed (idx 3)
  const doneAfter = [2, 2, 3];
  const activeAt = [1, -1, 2]; // -1 = chunking has no own status bucket

  if (currentIdx >= doneAfter[stepIndex]) return 'done';
  if (currentIdx === activeAt[stepIndex]) return 'active';
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
    embedding: { label: 'Embedding', variant: 'default' },
    scoring: { label: 'Scoring', variant: 'default' },
    completed: { label: 'Completed', variant: 'outline' },
    failed: { label: 'Failed', variant: 'destructive' },
    book_picked: { label: 'Book picked', variant: 'outline' },
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
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
          <h3 className="text-lg font-semibold">Chunking Analysis</h3>
          <p className="text-sm text-muted-foreground">
            Extract, chunk, and embed book PDFs so you can visualise coverage
            later.
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

      {/* Progress card — shown when there's an active or completed run */}
      {run && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Pipeline progress</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* Step indicators */}
            <div className="grid grid-cols-3 gap-4">
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

            {/* Completed summary */}
            {(run.status === 'completed' || run.status === 'book_picked') && (
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
    </div>
  );
}
