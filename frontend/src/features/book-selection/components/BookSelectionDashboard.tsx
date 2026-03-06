import { useState, useEffect, useCallback, useRef } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import type {
  BookCandidate,
  BookSelectionSession,
  CourseSelectedBook,
  SessionStatus,
  StartSessionRequest,
} from '../types';
import {
  createSession,
  getCourseSelectedBooks,
  getLatestSession,
  getSession,
  getSessionBooks,
  runDiscovery,
  resumeScoring,
  selectAndDownload,
} from '../api';
import { WeightsConfigPanel } from './WeightsConfigPanel';
import { DiscoveryScoringProgress } from './DiscoveryScoringProgress';
import { BookReviewTable } from './BookReviewTable';
import { DownloadStatusPanel } from './DownloadStatusPanel';
import { ManualUploadCard } from './ManualUploadCard';

/** Statuses where the backend is actively working and we should poll. */
const ACTIVE_STATUSES: SessionStatus[] = [
  'discovering',
  'scoring',
  'downloading',
];

/** Terminal + review statuses that stop polling. */
const TERMINAL_STATUSES: SessionStatus[] = [
  'awaiting_review',
  'completed',
  'failed',
  'superseded',
];

const POLL_INTERVAL_MS = 3000;

interface BookSelectionDashboardProps {
  courseId: number;
  disabled?: boolean;
}

export function BookSelectionDashboard({
  courseId,
  disabled,
}: BookSelectionDashboardProps) {
  // ── State ────────────────────────────────────────────────────
  const [session, setSession] = useState<BookSelectionSession | null>(null);
  const [books, setBooks] = useState<BookCandidate[]>([]);
  const [selectedBooks, setSelectedBooks] = useState<CourseSelectedBook[]>([]);
  const [phase, setPhase] = useState<SessionStatus>('configuring');
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Polling ──────────────────────────────────────────────────

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (sessionId: number) => {
      stopPolling();
      pollRef.current = setInterval(async () => {
        try {
          const updated = await getSession(sessionId);
          setSession(updated);
          setPhase(updated.status);

          // When we reach a terminal/review status, fetch final data and stop
          if (TERMINAL_STATUSES.includes(updated.status)) {
            stopPolling();
            setIsLoading(false);
            setIsSubmitting(false);

            if (updated.status === 'awaiting_review') {
              const bks = await getSessionBooks(sessionId);
              setBooks(bks);
            }

            if (
              updated.status === 'completed' ||
              updated.status === 'downloading'
            ) {
              const bks = await getSessionBooks(sessionId);
              setBooks(bks);
              const selBks = await getCourseSelectedBooks(courseId);
              setSelectedBooks(selBks);
            }

            if (updated.status === 'failed' && updated.error_message) {
              setError(updated.error_message);
              toast.error(updated.error_message);
            }
          }
        } catch {
          // Transient polling error — ignore, will retry next tick
        }
      }, POLL_INTERVAL_MS);
    },
    [courseId, stopPolling],
  );

  // ── Cleanup on unmount ──────────────────────────────────────
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // ── Load existing session on mount ──────────────────────────
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const existing = await getLatestSession(courseId);
        if (cancelled) return;
        if (existing) {
          setSession(existing);
          setPhase(existing.status);

          if (
            existing.status === 'awaiting_review' ||
            existing.status === 'downloading' ||
            existing.status === 'completed'
          ) {
            const bks = await getSessionBooks(existing.id);
            if (!cancelled) setBooks(bks);
          }

          if (
            existing.status === 'downloading' ||
            existing.status === 'completed'
          ) {
            const selBks = await getCourseSelectedBooks(courseId);
            if (!cancelled) setSelectedBooks(selBks);
          }

          // Auto-resume if session was interrupted mid-work
          if (ACTIVE_STATUSES.includes(existing.status)) {
            setIsLoading(true);
            startPolling(existing.id);
          }

          if (existing.status === 'failed' && existing.error_message) {
            setError(existing.error_message);
          }
        }
      } catch {
        // Session doesn't exist yet — show config panel
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [courseId, startPolling]);

  // ── Handlers ────────────────────────────────────────────────

  const handleStart = useCallback(
    async (request: StartSessionRequest) => {
      setIsLoading(true);
      setError(null);

      try {
        const newSession = await createSession(courseId, request);
        setSession(newSession);
        setPhase('discovering');

        await runDiscovery(newSession.id);
        startPolling(newSession.id);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : 'Failed to start session';
        setError(msg);
        setPhase('failed');
        setIsLoading(false);
        toast.error(msg);
      }
    },
    [courseId, startPolling],
  );

  const handleResume = useCallback(
    async (sessionToResume: BookSelectionSession) => {
      setIsLoading(true);
      setError(null);

      try {
        await resumeScoring(sessionToResume.id);
        setPhase('scoring');
        startPolling(sessionToResume.id);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : 'Failed to resume scoring';
        setError(msg);
        setPhase('failed');
        setIsLoading(false);
        toast.error(msg);
      }
    },
    [startPolling],
  );

  const handleSelect = useCallback(
    async (selectedIds: number[]) => {
      if (!session) return;
      setIsSubmitting(true);
      setPhase('downloading');

      try {
        await selectAndDownload(session.id, selectedIds);
        startPolling(session.id);
      } catch (err) {
        const msg =
          err instanceof Error ? err.message : 'Failed to start downloads';
        setError(msg);
        setPhase('failed');
        setIsSubmitting(false);
        toast.error(msg);
      }
    },
    [session, startPolling],
  );

  const refreshBooks = useCallback(async () => {
    if (!session) return;
    try {
      const bks = await getSessionBooks(session.id);
      setBooks(bks);
    } catch {
      /* silent */
    }
    try {
      const selBks = await getCourseSelectedBooks(courseId);
      setSelectedBooks(selBks);
    } catch {
      /* silent */
    }
  }, [session, courseId]);

  const handleCustomUpload = useCallback(
    (book: CourseSelectedBook) => {
      setSelectedBooks((prev) => [...prev, book]);
    },
    [],
  );

  // ── Render ──────────────────────────────────────────────────

  if (disabled) {
    return (
      <Alert className="bg-muted/50">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Extraction required</AlertTitle>
        <AlertDescription>
          Run extraction first so the AI can analyze your course content and find
          relevant textbooks.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-4">
            <span>{error}</span>
            {phase === 'failed' && session && (
              <Button
                variant="outline"
                size="sm"
                className="shrink-0 border-destructive/50 text-destructive hover:bg-destructive/10"
                onClick={() => {
                  setError(null);
                  handleResume(session);
                }}
                disabled={isLoading}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Retry
              </Button>
            )}
          </AlertDescription>
        </Alert>
      )}

      {/* Phase: Configuration (or failed - allow retry) */}
      {(phase === 'configuring' || (phase === 'failed' && !session)) && (
        <WeightsConfigPanel
          onStart={handleStart}
          isLoading={isLoading}
          disabled={disabled}
        />
      )}

      {/* Phase: Failed with existing session — show retry options */}
      {phase === 'failed' && session && !error && (
        <Alert className="bg-muted/50">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Session failed</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-4">
            <span>The previous scoring session encountered an error. You can retry or start fresh.</span>
            <div className="flex gap-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  handleResume(session);
                }}
                disabled={isLoading}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                Retry
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSession(null);
                  setPhase('configuring');
                  setError(null);
                }}
              >
                Start fresh
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      )}

      {/* Phase: Discovery / Scoring */}
      {(phase === 'discovering' || phase === 'scoring') && (
        <DiscoveryScoringProgress
          phase={phase}
          session={session}
        />
      )}

      {/* Phase: Review */}
      {phase === 'awaiting_review' && (
        <BookReviewTable
          books={books}
          onSelect={handleSelect}
          isSubmitting={isSubmitting}
          weightsJson={session?.weights_json}
        />
      )}

      {/* Phase: Downloading */}
      {(phase === 'downloading' || phase === 'completed') && session && (
        <>
          <DownloadStatusPanel
            selectedBooks={selectedBooks}
            downloadEvents={[]}
            isDownloading={phase === 'downloading'}
            onRefresh={refreshBooks}
          />
          <ManualUploadCard
            courseId={courseId}
            onUploaded={handleCustomUpload}
          />
        </>
      )}

    </div>
  );
}
