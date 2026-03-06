import { useCallback, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Eye,
  FileText,
  Hash,
  Loader2,
  Play,
  ScrollText,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Separator } from '@/components/ui/separator';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import {
  approveExtraction,
  getExtractionPreview,
  getLatestAnalysis,
  triggerExtractionOnly,
} from '../../api';
import type {
  BookExtractionPreview,
  BookExtractionRun,
  ChapterPreview,
  ExtractionPreviewResponse,
  SectionPreview,
} from '../../types';

// ── Helpers ────────────────────────────────────────────────────

function formatChars(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function contentQuality(content: string): 'good' | 'sparse' | 'empty' {
  const trimmed = content.trim();
  if (!trimmed) return 'empty';
  if (trimmed.length < 200) return 'sparse';
  return 'good';
}

const QUALITY_COLORS = {
  good: 'text-green-600 dark:text-green-400',
  sparse: 'text-amber-600 dark:text-amber-400',
  empty: 'text-red-500 dark:text-red-400',
} as const;

const QUALITY_BG = {
  good: 'bg-green-50 border-green-200 dark:bg-green-950/20 dark:border-green-800',
  sparse: 'bg-amber-50 border-amber-200 dark:bg-amber-950/20 dark:border-amber-800',
  empty: 'bg-red-50 border-red-200 dark:bg-red-950/20 dark:border-red-800',
} as const;

// ── Section Component ──────────────────────────────────────────

function SectionItem({ section }: { section: SectionPreview }) {
  const [expanded, setExpanded] = useState(false);
  const quality = contentQuality(section.content);

  return (
    <div className={`rounded-md border p-3 ${QUALITY_BG[quality]}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 text-left"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="flex-1 text-sm font-medium truncate">
          {section.section_title}
        </span>
        <span className={`text-xs tabular-nums ${QUALITY_COLORS[quality]}`}>
          {formatChars(section.content_length)}
        </span>
        {quality === 'empty' && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
              </TooltipTrigger>
              <TooltipContent>No content extracted for this section</TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
      </button>

      {expanded && (
        <div className="mt-2 pl-5 overflow-hidden">
          {section.content.trim() ? (
            <div className="max-h-64 overflow-auto rounded-md">
              <pre className="whitespace-pre-wrap text-xs leading-relaxed text-foreground/80 font-mono p-2">
                {section.content.slice(0, 3000)}
                {section.content.length > 3000 && (
                  <span className="text-muted-foreground">
                    {'\n'}… ({formatChars(section.content.length - 3000)} more)
                  </span>
                )}
              </pre>
            </div>
          ) : (
            <p className="text-xs italic text-red-500">
              No content extracted
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ── Chapter Component ──────────────────────────────────────────

function ChapterItem({ chapter }: { chapter: ChapterPreview }) {
  const [open, setOpen] = useState(false);
  const quality = contentQuality(chapter.content);
  const emptySections = chapter.sections.filter((s) => !s.has_content).length;

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center gap-3 rounded-lg border bg-card p-4 text-left hover:bg-accent/50 transition-colors">
          {open ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="shrink-0 tabular-nums text-xs">
                Ch. {chapter.chapter_index}
              </Badge>
              <span className="font-medium truncate">{chapter.chapter_title}</span>
            </div>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 text-xs text-muted-foreground">
                    <ScrollText className="h-3.5 w-3.5" />
                    <span className="tabular-nums">{chapter.section_count}</span>
                  </div>
                </TooltipTrigger>
                <TooltipContent>{chapter.section_count} sections</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            {emptySections > 0 && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant="destructive" className="text-xs">
                      {emptySections} empty
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    {emptySections} section(s) have no extracted content
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}

            <span className={`text-xs tabular-nums ${QUALITY_COLORS[quality]}`}>
              {formatChars(chapter.content_length)}
            </span>
          </div>
        </button>
      </CollapsibleTrigger>

      <CollapsibleContent className="overflow-hidden">
        <div className="ml-4 mt-2 space-y-2 border-l-2 border-muted pl-4 pb-2">
          {chapter.sections.length > 0 ? (
            chapter.sections.map((sec, i) => (
              <SectionItem key={i} section={sec} />
            ))
          ) : (
            <p className="text-sm text-muted-foreground italic py-2">
              No sections detected — content exists only at chapter level
            </p>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

// ── Book Component ─────────────────────────────────────────────

function BookPreviewCard({ book }: { book: BookExtractionPreview }) {
  const [expanded, setExpanded] = useState(true);
  const emptyChapters = book.chapters.filter((ch) => !ch.has_content).length;
  const totalEmptySections = book.chapters.reduce(
    (acc, ch) => acc + ch.sections.filter((s) => !s.has_content).length,
    0,
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <BookOpen className="h-4 w-4 text-primary" />
              {book.book_title}
            </CardTitle>
            {book.authors && (
              <p className="text-sm text-muted-foreground">{book.authors}</p>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setExpanded(!expanded)}
            className="shrink-0"
          >
            {expanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap gap-4 pt-2">
          <div className="flex items-center gap-1.5 text-sm">
            <Hash className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{book.total_chapters}</span>
            <span className="text-muted-foreground">chapters</span>
          </div>
          <div className="flex items-center gap-1.5 text-sm">
            <ScrollText className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{book.total_sections}</span>
            <span className="text-muted-foreground">sections</span>
          </div>
          <div className="flex items-center gap-1.5 text-sm">
            <FileText className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{formatChars(book.total_content_chars)}</span>
            <span className="text-muted-foreground">chars</span>
          </div>
          {emptyChapters > 0 && (
            <Badge variant="destructive" className="text-xs">
              {emptyChapters} empty chapter(s)
            </Badge>
          )}
          {totalEmptySections > 0 && (
            <Badge variant="outline" className="text-xs border-amber-300 text-amber-600">
              {totalEmptySections} empty section(s)
            </Badge>
          )}
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="pt-0">
          <Separator className="mb-4" />
          <div className="space-y-2">
            {book.chapters.map((ch, i) => (
              <ChapterItem key={i} chapter={ch} />
            ))}
            {book.chapters.length === 0 && (
              <Alert variant="destructive">
                <XCircle className="h-4 w-4" />
                <AlertTitle>No chapters extracted</AlertTitle>
                <AlertDescription>
                  The PDF extraction could not detect any chapters. The book may
                  have a non-standard structure or corrupted text layer.
                </AlertDescription>
              </Alert>
            )}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ── Main Component ─────────────────────────────────────────────

interface ExtractionInspectorProps {
  courseId: number;
  disabled?: boolean;
}

export function ExtractionInspector({ courseId, disabled }: ExtractionInspectorProps) {
  const [run, setRun] = useState<BookExtractionRun | null>(null);
  const [preview, setPreview] = useState<ExtractionPreviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
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

          // Stop polling when extraction finishes or fails
          if (['chapter_extracted', 'failed', 'completed', 'book_picked', 'agentic_completed'].includes(latest.status)) {
            stopPolling();

            // Auto-load preview when extraction is done
            if (latest.status === 'chapter_extracted') {
              const previewData = await getExtractionPreview(cId, latest.id);
              setPreview(previewData);
            }
          }
        } catch {
          // Transient poll error
        }
      }, 3000);
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

        // If there's an existing run with chapters, load preview
        if (latest && ['chapter_extracted', 'completed', 'book_picked', 'agentic_completed', 'agentic_extracting'].includes(latest.status)) {
          const previewData = await getExtractionPreview(courseId, latest.id);
          if (!cancelled) setPreview(previewData);
        }

        // If extraction is in progress, start polling
        if (latest && ['pending', 'extracting'].includes(latest.status)) {
          startPolling(courseId);
        }
      } catch {
        if (!cancelled) setError('Failed to load extraction status.');
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [courseId, startPolling]);

  // ── Actions ────────────────────────────────────────────────

  const handleExtract = async () => {
    setIsExtracting(true);
    setError(null);
    setPreview(null);
    try {
      const newRun = await triggerExtractionOnly(courseId);
      setRun(newRun);

      // If already extracted (reused existing run), load preview immediately
      if (newRun.status === 'chapter_extracted') {
        const previewData = await getExtractionPreview(courseId, newRun.id);
        setPreview(previewData);
      } else {
        startPolling(courseId);
      }
      toast.success('PDF extraction started');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start extraction';
      setError(msg);
      toast.error(msg);
    } finally {
      setIsExtracting(false);
    }
  };

  const handleApprove = async () => {
    if (!run) return;
    setIsApproving(true);
    setError(null);
    try {
      const updated = await approveExtraction(courseId, run.id);
      setRun(updated);
      toast.success('Extraction approved — chunking pipeline started');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to approve';
      setError(msg);
      toast.error(msg);
    } finally {
      setIsApproving(false);
    }
  };

  // ── Derived state ──────────────────────────────────────────

  const isActive = run && ['pending', 'extracting'].includes(run.status);
  const canApprove = run?.status === 'chapter_extracted';
  const alreadyApproved = run && ['chunking', 'embedding', 'scoring', 'completed', 'book_picked', 'agentic_extracting', 'agentic_completed'].includes(run.status);

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
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <Eye className="h-5 w-5 text-primary" />
            Extraction Inspector
          </h3>
          <p className="text-sm text-muted-foreground">
            Extract PDFs, inspect chapters & sections, then approve to continue.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {run && (
            <Badge variant={run.status === 'failed' ? 'destructive' : run.status === 'chapter_extracted' ? 'default' : 'secondary'}>
              {run.status === 'chapter_extracted' ? 'Ready for review' : run.status}
            </Badge>
          )}

          {!alreadyApproved && (
            <Button
              onClick={handleExtract}
              disabled={disabled || isExtracting || !!isActive}
              size="sm"
            >
              {isExtracting || isActive ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {run ? 'Re-extract' : 'Extract PDFs'}
            </Button>
          )}

          {canApprove && (
            <Button
              onClick={handleApprove}
              disabled={isApproving}
              variant="default"
              size="sm"
              className="bg-green-600 hover:bg-green-700"
            >
              {isApproving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Check className="mr-2 h-4 w-4" />
              )}
              Approve & Continue
            </Button>
          )}

          {alreadyApproved && (
            <Badge variant="outline" className="border-green-500 text-green-600">
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
              Approved
            </Badge>
          )}
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

      {/* Extraction in progress */}
      {isActive && (
        <Card>
          <CardContent className="flex items-center gap-4 py-8">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <div>
              <p className="font-medium">Extracting PDFs…</p>
              <p className="text-sm text-muted-foreground">
                {run?.progress_detail || 'Processing books…'}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Failed */}
      {run?.status === 'failed' && run.error_message && (
        <Alert variant="destructive">
          <XCircle className="h-4 w-4" />
          <AlertTitle>Extraction failed</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">
            {run.error_message}
          </AlertDescription>
        </Alert>
      )}

      {/* Preview */}
      {preview && preview.books.length > 0 && (
        <div className="space-y-4">
          {/* Summary bar */}
          <Card>
            <CardContent className="py-4">
              <div className="flex flex-wrap items-center gap-6">
                <div className="text-center">
                  <p className="text-2xl font-bold">{preview.books.length}</p>
                  <p className="text-xs text-muted-foreground">Books</p>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div className="text-center">
                  <p className="text-2xl font-bold">
                    {preview.books.reduce((a, b) => a + b.total_chapters, 0)}
                  </p>
                  <p className="text-xs text-muted-foreground">Chapters</p>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div className="text-center">
                  <p className="text-2xl font-bold">
                    {preview.books.reduce((a, b) => a + b.total_sections, 0)}
                  </p>
                  <p className="text-xs text-muted-foreground">Sections</p>
                </div>
                <Separator orientation="vertical" className="h-10" />
                <div className="text-center">
                  <p className="text-2xl font-bold">
                    {formatChars(preview.books.reduce((a, b) => a + b.total_content_chars, 0))}
                  </p>
                  <p className="text-xs text-muted-foreground">Total text</p>
                </div>

                {/* Quality indicators */}
                {preview.books.some((b) =>
                  b.chapters.some((ch) => !ch.has_content),
                ) && (
                  <>
                    <Separator orientation="vertical" className="h-10" />
                    <div className="flex items-center gap-2 text-amber-600">
                      <AlertTriangle className="h-4 w-4" />
                      <span className="text-sm font-medium">
                        {preview.books.reduce(
                          (a, b) => a + b.chapters.filter((ch) => !ch.has_content).length,
                          0,
                        )}{' '}
                        empty chapter(s)
                      </span>
                    </div>
                  </>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Books */}
          {preview.books.map((book) => (
            <BookPreviewCard key={book.book_id} book={book} />
          ))}
        </div>
      )}

      {/* No books */}
      {preview && preview.books.length === 0 && (
        <Alert>
          <FileText className="h-4 w-4" />
          <AlertTitle>No books found</AlertTitle>
          <AlertDescription>
            No selected books with uploaded PDFs were found. Please upload books
            first in the Book Selection step.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
