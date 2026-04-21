import { memo, useCallback, useEffect, useRef, useState } from 'react';
import {
  Bot,
  BookOpen,
  CheckCircle2,
  Loader2,
  Play,
  XCircle,
  Sparkles,
  Brain,
  FileSearch,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import { openAgenticExtractionStream } from '../../api';
import type {
  AgenticStreamEvent,
  AgenticAgentStatus,
  ExtractionRunStatus,
} from '../../types';

// ── Constants ──────────────────────────────────────────────────

const WORKER_COUNT = 5;

// ── Agent slot state ───────────────────────────────────────────

interface AgentSlot {
  id: number;
  state: 'idle' | 'working' | 'done' | 'error';
  chapterTitle?: string;
  chapterNumber?: number;
  step?: AgenticAgentStatus['step'];
  iteration?: number;
  conceptCount?: number;
  approved?: boolean;
}

interface BookProgress {
  bookId: number;
  bookTitle: string;
  bookIndex: number;
  totalBooks: number;
  totalChapters: number;
  chapterTitles: string[];
  completedChapters: number;
  totalConcepts: number;
  errors: string[];
}

interface AgenticLog {
  ts: number;
  text: string;
  kind: 'info' | 'success' | 'error';
}

// ── Step icon helper ───────────────────────────────────────────

function StepIcon({ step }: { step?: AgenticAgentStatus['step'] }) {
  switch (step) {
    case 'extracting':
      return <FileSearch className="h-3.5 w-3.5" />;
    case 'evaluated':
      return <Brain className="h-3.5 w-3.5" />;
    case 'skills':
      return <Sparkles className="h-3.5 w-3.5" />;
    default:
      return <Bot className="h-3.5 w-3.5" />;
  }
}

function stepLabel(step?: AgenticAgentStatus['step']) {
  switch (step) {
    case 'extracting':
      return 'Extracting concepts';
    case 'evaluated':
      return 'Evaluating quality';
    case 'skills':
      return 'Mapping skills';
    default:
      return 'Idle';
  }
}

// ── Component ──────────────────────────────────────────────────

interface AgenticAnalysisProps {
  courseId: number;
  runId: number;
  runStatus: ExtractionRunStatus;
  onStatusChange?: (status: ExtractionRunStatus) => void;
}

export function AgenticAnalysis({
  courseId,
  runId,
  runStatus,
  onStatusChange,
}: AgenticAnalysisProps) {
  const [agents, setAgents] = useState<AgentSlot[]>(
    () => Array.from({ length: WORKER_COUNT }, (_, i) => ({
      id: i,
      state: 'idle' as const,
    })),
  );
  const [books, setBooks] = useState<BookProgress[]>([]);
  const [currentBookId, setCurrentBookId] = useState<number | null>(null);
  const [logs, setLogs] = useState<AgenticLog[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isDone, setIsDone] = useState(
    runStatus === 'agentic_completed',
  );
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [totalStats, setTotalStats] = useState({ books: 0, chapters: 0, concepts: 0 });

  // Derived: backend is extracting but we have no SSE connection (e.g. page refresh)
  const backgroundRunning = runStatus === 'agentic_extracting' && !isRunning;

  const sseRef = useRef<AbortController | null>(null);
  const agentMapRef = useRef(new Map<string, number>());
  const logsEndRef = useRef<HTMLDivElement>(null);
  const agentSlotsRef = useRef<AgentSlot[] | null>(null);
  if (agentSlotsRef.current === null) {
    agentSlotsRef.current = Array.from({ length: WORKER_COUNT }, (_, i) => ({ id: i, state: 'idle' as const }));
  }
  const doneTimersRef = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const onStatusChangeRef = useRef(onStatusChange);
  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  const addLog = useCallback(
    (text: string, kind: AgenticLog['kind'] = 'info') => {
      setLogs((prev) => [...prev.slice(-200), { ts: Date.now(), text, kind }]);
    },
    [],
  );

  // Helper to keep ref in sync with React state
  const updateAgents = useCallback(
    (updater: (prev: AgentSlot[]) => AgentSlot[]) => {
      setAgents((prev) => {
        const next = updater(prev);
        agentSlotsRef.current = next;
        return next;
      });
    },
    [],
  );

  const resetAgents = useCallback(() => {
    const fresh = Array.from({ length: WORKER_COUNT }, (_, i) => ({
      id: i,
      state: 'idle' as const,
    }));
    agentSlotsRef.current = fresh;
    setAgents(fresh);
    for (const timer of doneTimersRef.current.values()) clearTimeout(timer);
    doneTimersRef.current.clear();
  }, []);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Assign a chapter to an agent slot — reads from ref for real-time accuracy
  const assignAgent = useCallback(
    (chapterKey: string): number => {
      const map = agentMapRef.current;
      if (map.has(chapterKey)) return map.get(chapterKey)!;

      const slots = agentSlotsRef.current;
      if (!slots) return map.size % WORKER_COUNT;

      // Slots already claimed by another chapter (map may be ahead of ref state)
      const claimed = new Set(map.values());

      // Prefer idle, then done — but skip slots already claimed by another chapter
      const idle = slots.find((a) => a.state === 'idle' && !claimed.has(a.id));
      const done = !idle
        ? slots.find((a) => a.state === 'done' && !claimed.has(a.id))
        : undefined;
      const target = idle ?? done;
      const slotId = target?.id ?? (map.size % WORKER_COUNT);

      // If reassigning a 'done' slot, cancel its pending idle-reset timer
      if (target?.state === 'done') {
        const timer = doneTimersRef.current.get(slotId);
        if (timer) {
          clearTimeout(timer);
          doneTimersRef.current.delete(slotId);
        }
        // Remove the old chapter→slot mapping
        for (const [k, v] of map.entries()) {
          if (v === slotId) { map.delete(k); break; }
        }
      }

      map.set(chapterKey, slotId);

      // Mark slot as 'working' in the ref immediately so subsequent calls
      // (within the same synchronous SSE batch) see the update even before
      // React flushes the batched setAgents updaters.
      if (slots[slotId]) {
        slots[slotId] = { ...slots[slotId], state: 'working' };
      }

      return slotId;
    },
    [],
  );

  const handleEvent = useCallback(
    (evt: AgenticStreamEvent) => {
      switch (evt.type) {
        case 'loading_book': {
          setCurrentBookId(evt.book_id);
          setBooks((prev) => {
            const exists = prev.find((b) => b.bookId === evt.book_id);
            if (exists) return prev;
            return [
              ...prev,
              {
                bookId: evt.book_id,
                bookTitle: evt.book_title,
                bookIndex: evt.book_index,
                totalBooks: evt.total_books,
                totalChapters: 0,
                chapterTitles: [],
                completedChapters: 0,
                totalConcepts: 0,
                errors: [],
              },
            ];
          });
          addLog(
            `Loading chapters for book ${evt.book_index + 1}/${evt.total_books}: "${evt.book_title}"…`,
          );
          break;
        }

        case 'book_started': {
          setCurrentBookId(evt.book_id);
          agentMapRef.current.clear();
          resetAgents();
          setBooks((prev) => {
            const exists = prev.find((b) => b.bookId === evt.book_id);
            if (exists) {
              // Update the placeholder entry created by loading_book
              return prev.map((b) =>
                b.bookId === evt.book_id
                  ? {
                      ...b,
                      totalChapters: evt.total_chapters,
                      chapterTitles: evt.chapter_titles ?? [],
                    }
                  : b,
              );
            }
            return [
              ...prev,
              {
                bookId: evt.book_id,
                bookTitle: evt.book_title,
                bookIndex: evt.book_index,
                totalBooks: evt.total_books,
                totalChapters: evt.total_chapters,
                chapterTitles: evt.chapter_titles ?? [],
                completedChapters: 0,
                totalConcepts: 0,
                errors: [],
              },
            ];
          });
          addLog(
            `Started book ${evt.book_index + 1}/${evt.total_books}: "${evt.book_title}" (${evt.total_chapters} chapters)`,
          );
          break;
        }

        case 'agent_status': {
          const key = `${evt.book_id}-${evt.chapter_number}`;
          const slotId = assignAgent(key);
          updateAgents((prev) =>
            prev.map((a) =>
              a.id === slotId
                ? {
                    ...a,
                    state: 'working' as const,
                    chapterTitle: evt.chapter_title,
                    chapterNumber: evt.chapter_number,
                    step: evt.step,
                    iteration: evt.iteration,
                    conceptCount: evt.concept_count,
                    approved: evt.approved,
                  }
                : a,
            ),
          );
          const detail =
            evt.step === 'extracting'
              ? `extracting concepts${evt.iteration ? ` (iteration ${evt.iteration})` : ''}`
              : evt.step === 'evaluated'
                ? `evaluated: ${evt.approved ? 'approved' : 'needs revision'}${evt.concept_count ? ` (${evt.concept_count} concepts)` : ''}`
                : `mapping skills`;
          addLog(
            `Agent #${slotId + 1} → Ch.${evt.chapter_number} "${evt.chapter_title}": ${detail}`,
          );
          break;
        }

        case 'chapter_completed': {
          const key = `${evt.book_id}-${evt.chapter_number}`;
          const slotId = agentMapRef.current.get(key);
          if (slotId !== undefined) {
            updateAgents((prev) =>
              prev.map((a) =>
                a.id === slotId
                  ? {
                      ...a,
                      state: 'done' as const,
                      conceptCount: evt.concept_count,
                      approved: evt.approved,
                    }
                  : a,
              ),
            );
            // Brief done flash, then free — assignAgent can steal this slot sooner if needed
            const timer = setTimeout(() => {
              agentMapRef.current.delete(key);
              doneTimersRef.current.delete(slotId);
              updateAgents((prev) =>
                prev.map((a) =>
                  a.id === slotId && a.state === 'done'
                    ? { id: slotId, state: 'idle' as const }
                    : a,
                ),
              );
            }, 500);
            doneTimersRef.current.set(slotId, timer);
          }
          setBooks((prev) =>
            prev.map((b) =>
              b.bookId === evt.book_id
                ? {
                    ...b,
                    completedChapters: b.completedChapters + 1,
                    totalConcepts: b.totalConcepts + evt.concept_count,
                  }
                : b,
            ),
          );
          addLog(
            `Completed Ch.${evt.chapter_number} "${evt.chapter_title}" — ${evt.concept_count} concepts, ${evt.skill_count} skills (${evt.elapsed_s.toFixed(1)}s)`,
            'success',
          );
          break;
        }

        case 'chapter_error': {
          const key = `${evt.book_id}-${evt.chapter_number}`;
          const slotId = agentMapRef.current.get(key);
          if (slotId !== undefined) {
            updateAgents((prev) =>
              prev.map((a) =>
                a.id === slotId
                  ? { ...a, state: 'error' as const }
                  : a,
              ),
            );
            const timer = setTimeout(() => {
              agentMapRef.current.delete(key);
              doneTimersRef.current.delete(slotId);
              updateAgents((prev) =>
                prev.map((a) =>
                  a.id === slotId && a.state === 'error'
                    ? { id: slotId, state: 'idle' as const }
                    : a,
                ),
              );
            }, 2000);
            doneTimersRef.current.set(slotId, timer);
          }
          setBooks((prev) =>
            prev.map((b) =>
              b.bookId === evt.book_id
                ? { ...b, errors: [...b.errors, evt.error] }
                : b,
            ),
          );
          addLog(
            `Error Ch.${evt.chapter_number} "${evt.chapter_title}": ${evt.error}`,
            'error',
          );
          break;
        }

        case 'book_completed': {
          setBooks((prev) =>
            prev.map((b) =>
              b.bookId === evt.book_id
                ? {
                    ...b,
                    completedChapters: evt.chapters_done,
                    totalConcepts: evt.total_concepts,
                  }
                : b,
            ),
          );
          addLog(
            `Book "${evt.book_title}" completed — ${evt.chapters_done} chapters, ${evt.total_concepts} concepts`,
            'success',
          );
          break;
        }

        case 'done': {
          setIsRunning(false);
          setIsDone(true);
          setTotalStats({
            books: evt.total_books,
            chapters: evt.total_chapters,
            concepts: evt.total_concepts,
          });
          resetAgents();
          addLog(
            `All done — ${evt.total_books} books, ${evt.total_chapters} chapters, ${evt.total_concepts} concepts`,
            'success',
          );
          onStatusChangeRef.current?.('agentic_completed');
          break;
        }

        case 'error': {
          setIsRunning(false);
          setGlobalError(evt.message);
          addLog(`Error: ${evt.message}`, 'error');
          break;
        }
      }
    },
    [addLog, assignAgent, updateAgents, resetAgents],
  );

  const startExtraction = useCallback(() => {
    if (sseRef.current) return;
    setIsRunning(true);
    setIsDone(false);
    setGlobalError(null);
    setLogs([]);
    setBooks([]);
    setTotalStats({ books: 0, chapters: 0, concepts: 0 });
    resetAgents();
    agentMapRef.current.clear();

    sseRef.current = openAgenticExtractionStream(
      courseId,
      runId,
      handleEvent,
      () => {
        sseRef.current = null;
        setIsRunning(false);
      },
      (err) => {
        setGlobalError(err instanceof Error ? err.message : String(err));
        setIsRunning(false);
      },
    );

    onStatusChangeRef.current?.('agentic_extracting');
  }, [courseId, runId, handleEvent, resetAgents]);

  // Cleanup SSE + timers on unmount
  useEffect(
    () => () => {
      sseRef.current?.abort();
      sseRef.current = null;
      for (const timer of doneTimersRef.current.values()) clearTimeout(timer);
      doneTimersRef.current.clear();
    },
    [],
  );

  // ── Current book shortcut ───────────────────────────────────

  const currentBook = books.find((b) => b.bookId === currentBookId);

  // ── Render ─────────────────────────────────────────────────

  // Sync isDone from parent polling (parent detects agentic_completed)
  const [prevRunStatus, setPrevRunStatus] = useState(runStatus);
  if (runStatus !== prevRunStatus) {
    setPrevRunStatus(runStatus);
    if (runStatus === 'agentic_completed' && !isDone) {
      setIsDone(true);
      setIsRunning(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-primary" />
          <h4 className="text-base font-semibold">Agentic Chapter Extraction</h4>
          {isDone && (
            <Badge variant="outline" className="ml-2 text-green-700 border-green-300">
              <CheckCircle2 className="mr-1 h-3 w-3" /> Completed
            </Badge>
          )}
          {(isRunning || backgroundRunning) && (
            <Badge variant="default" className="ml-2">
              <Loader2 className="mr-1 h-3 w-3 animate-spin" /> Running
            </Badge>
          )}
        </div>
        <Button
          size="sm"
          onClick={startExtraction}
          disabled={isRunning || backgroundRunning}
        >
          {(isRunning || backgroundRunning) ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          {isDone ? 'Re-run extraction' : 'Start extraction'}
        </Button>
      </div>

      <p className="text-sm text-muted-foreground">
        Deep chapter-level analysis using {WORKER_COUNT} parallel AI agents — extracts
        concepts, evaluates quality, and maps skills from each chapter.
      </p>

      {/* Background extraction banner */}
      {backgroundRunning && !isRunning && (
        <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex items-center gap-3">
          <Loader2 className="h-5 w-5 animate-spin text-primary flex-shrink-0" />
          <div>
            <p className="text-sm font-medium">Extraction is running in the background</p>
            <p className="text-xs text-muted-foreground">
              The AI agents are processing your books on the server. This page will
              update automatically when finished. You can safely navigate away.
            </p>
          </div>
        </div>
      )}

      {/* Global error */}
      {globalError && (
        <div className="rounded-lg border border-destructive/50 bg-destructive/5 p-3 text-sm text-destructive">
          <XCircle className="mr-2 inline h-4 w-4" />
          {globalError}
        </div>
      )}

      {/* Done summary */}
      {isDone && totalStats.books > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <SummaryCard label="Books" value={totalStats.books} icon={BookOpen} />
          <SummaryCard label="Chapters" value={totalStats.chapters} icon={FileSearch} />
          <SummaryCard label="Concepts" value={totalStats.concepts} icon={Brain} />
        </div>
      )}

      {/* Agent grid + book progress — only when started */}
      {(isRunning || books.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-5">
          {/* Book Progress — left panel */}
          <div className="lg:col-span-2 space-y-3">
            <h5 className="text-sm font-medium text-muted-foreground">Book Progress</h5>
            {books.map((book) => {
              const pct =
                book.totalChapters > 0
                  ? Math.round(
                      (book.completedChapters / book.totalChapters) * 100,
                    )
                  : 0;
              const isCurrent = book.bookId === currentBookId;
              return (
                <Card
                  key={book.bookId}
                  className={`transition-colors ${isCurrent ? 'border-primary/60' : ''}`}
                >
                  <CardContent className="p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium truncate max-w-[70%]">
                        {book.bookTitle}
                      </span>
                      {book.totalChapters > 0 ? (
                        <span className="text-xs tabular-nums text-muted-foreground">
                          {book.completedChapters}/{book.totalChapters}
                        </span>
                      ) : (
                        <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                      )}
                    </div>
                    {book.totalChapters > 0 ? (
                      <Progress value={pct} className="h-1.5" />
                    ) : (
                      <p className="text-xs text-muted-foreground animate-pulse">
                        Loading chapters…
                      </p>
                    )}
                    {book.errors.length > 0 && (
                      <p className="text-xs text-destructive">
                        {book.errors.length} chapter error
                        {book.errors.length > 1 ? 's' : ''}
                      </p>
                    )}
                  </CardContent>
                </Card>
              );
            })}
            {books.length === 0 && isRunning && (
              <p className="text-xs text-muted-foreground animate-pulse">
                Connecting to pipeline…
              </p>
            )}
          </div>

          {/* Agent Cards — right panel */}
          <div className="lg:col-span-3 space-y-3">
            <h5 className="text-sm font-medium text-muted-foreground">
              AI Agents ({agents.filter((a) => a.state === 'working').length} active)
            </h5>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              <TooltipProvider>
                {agents.map((agent) => (
                  <AgentCard key={agent.id} agent={agent} />
                ))}
              </TooltipProvider>
            </div>

            {/* Current book chapter list */}
            {currentBook && currentBook.chapterTitles.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs text-muted-foreground">
                    Chapters — {currentBook.bookTitle}
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-3 pt-0">
                  <div className="flex flex-wrap gap-1.5">
                    {currentBook.chapterTitles.map((title, i) => {
                      const chNum = i + 1;
                      const isDone = agents.some(
                        (a) =>
                          a.chapterNumber === chNum &&
                          (a.state === 'done'),
                      );
                      const isWorking = agents.some(
                        (a) =>
                          a.chapterNumber === chNum && a.state === 'working',
                      );
                      return (
                        <Tooltip key={i}>
                          <TooltipTrigger asChild>
                            <Badge
                              variant={
                                isDone
                                  ? 'default'
                                  : isWorking
                                    ? 'secondary'
                                    : 'outline'
                              }
                              className={`text-xs cursor-default ${
                                isDone ? 'bg-green-600 hover:bg-green-700' : ''
                              } ${isWorking ? 'animate-pulse' : ''}`}
                            >
                              {chNum}
                            </Badge>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-xs">
                            <p className="text-xs">{title}</p>
                          </TooltipContent>
                        </Tooltip>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* Activity log */}
      {logs.length > 0 && (
        <>
          <Separator />
          <div>
            <h5 className="mb-2 text-sm font-medium text-muted-foreground">
              Activity Log
            </h5>
            <ScrollArea className="h-48 rounded-md border bg-muted/20 p-3">
              <div className="space-y-1 font-mono text-xs">
                {logs.map((log, i) => (
                  <div
                    key={i}
                    className={
                      log.kind === 'error'
                        ? 'text-destructive'
                        : log.kind === 'success'
                          ? 'text-green-700 dark:text-green-400'
                          : 'text-muted-foreground'
                    }
                  >
                    <span className="mr-2 opacity-40">
                      {new Date(log.ts).toLocaleTimeString()}
                    </span>
                    {log.text}
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </ScrollArea>
          </div>
        </>
      )}
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────

const AgentCard = memo(function AgentCard({ agent }: { agent: AgentSlot }) {
  const borderColor =
    agent.state === 'working'
      ? 'border-primary/60 bg-primary/5'
      : agent.state === 'done'
        ? 'border-green-500/40 bg-green-50 dark:bg-green-950/20'
        : agent.state === 'error'
          ? 'border-destructive/40 bg-destructive/5'
          : 'border-muted';

  return (
    <Card className={`transition-all duration-300 ${borderColor}`}>
      <CardContent className="p-3 space-y-1.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Bot
              className={`h-4 w-4 ${
                agent.state === 'working'
                  ? 'text-primary'
                  : agent.state === 'done'
                    ? 'text-green-600'
                    : agent.state === 'error'
                      ? 'text-destructive'
                      : 'text-muted-foreground'
              }`}
            />
            <span className="text-xs font-semibold">Agent #{agent.id + 1}</span>
          </div>
          {agent.state === 'working' && (
            <Loader2 className="h-3 w-3 animate-spin text-primary" />
          )}
          {agent.state === 'done' && (
            <CheckCircle2 className="h-3 w-3 text-green-600" />
          )}
          {agent.state === 'error' && (
            <XCircle className="h-3 w-3 text-destructive" />
          )}
        </div>

        {agent.state === 'idle' && (
          <p className="text-xs text-muted-foreground">Waiting for work…</p>
        )}

        {agent.state === 'working' && (
          <>
            <Tooltip>
              <TooltipTrigger asChild>
                <p className="text-xs truncate font-medium">
                  Ch.{agent.chapterNumber} — {agent.chapterTitle}
                </p>
              </TooltipTrigger>
              <TooltipContent side="top" className="max-w-xs">
                <p className="text-xs">
                  {agent.chapterTitle}
                </p>
              </TooltipContent>
            </Tooltip>
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <StepIcon step={agent.step} />
              <span>{stepLabel(agent.step)}</span>
            </div>
          </>
        )}

        {agent.state === 'done' && (
          <p className="text-xs text-green-700 dark:text-green-400">
            {agent.conceptCount ?? 0} concepts extracted
            {agent.approved ? '' : ' (revised)'}
          </p>
        )}

        {agent.state === 'error' && (
          <p className="text-xs text-destructive">Processing failed</p>
        )}
      </CardContent>
    </Card>
  );
});

function SummaryCard({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <Icon className="h-8 w-8 text-primary/60" />
        <div>
          <p className="text-2xl font-bold tabular-nums">{value}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}
