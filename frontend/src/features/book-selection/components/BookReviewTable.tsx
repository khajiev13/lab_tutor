import { useState, useMemo, Fragment } from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  BookOpen,
  Trophy,
  Star,
  RefreshCw,
} from 'lucide-react';
import type { BookCandidate, WeightsConfig } from '../types';
import { parseScores, SCORE_CRITERIA, DEFAULT_WEIGHTS } from '../types';

// ── Color helpers ──────────────────────────────────────────────

function scoreColor(value: number): string {
  if (value >= 0.8) return 'text-emerald-600 dark:text-emerald-400';
  if (value >= 0.6) return 'text-blue-600 dark:text-blue-400';
  if (value >= 0.4) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-500 dark:text-red-400';
}

function badgeVariant(
  value: number,
): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (value >= 0.8) return 'default';
  if (value >= 0.6) return 'secondary';
  return 'outline';
}

function rankIcon(idx: number) {
  if (idx === 0)
    return <Trophy className="h-4 w-4 text-amber-500" />;
  if (idx === 1)
    return <Trophy className="h-4 w-4 text-slate-400" />;
  if (idx === 2)
    return <Trophy className="h-4 w-4 text-amber-700" />;
  return (
    <span className="text-xs text-muted-foreground tabular-nums font-medium w-4 text-center">
      {idx + 1}
    </span>
  );
}

// ── Props ──────────────────────────────────────────────────────

interface BookReviewTableProps {
  books: BookCandidate[];
  maxSelections?: number;
  onSelect: (selectedIds: number[]) => void;
  onRediscover?: () => void;
  isSubmitting: boolean;
  isRediscovering?: boolean;
  weightsJson?: string | null;
}

export function BookReviewTable({
  books,
  maxSelections = 5,
  onSelect,
  onRediscover,
  isSubmitting,
  isRediscovering,
  weightsJson,
}: BookReviewTableProps) {
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const weights: WeightsConfig = useMemo(() => {
    if (!weightsJson) return DEFAULT_WEIGHTS;
    try {
      return JSON.parse(weightsJson) as WeightsConfig;
    } catch {
      return DEFAULT_WEIGHTS;
    }
  }, [weightsJson]);

  const toggleBook = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < maxSelections) {
        next.add(id);
      }
      return next;
    });
  };

  const toggleExpand = (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const sorted = [...books].sort(
    (a, b) => (b.s_final ?? 0) - (a.s_final ?? 0),
  );

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-4">
          <div>
            <CardTitle className="text-lg flex items-center gap-2">
              <BookOpen className="h-5 w-5 text-primary" />
              Book Candidates
            </CardTitle>
            <CardDescription className="mt-1">
              Review AI-scored books and select up to {maxSelections} to
              download. Click a row to expand the detailed score breakdown.
            </CardDescription>
          </div>
          <Button
            onClick={() => onSelect(Array.from(selectedIds))}
            disabled={selectedIds.size === 0 || isSubmitting}
            size="lg"
          >
            <CheckCircle2 className="mr-2 h-4 w-4" />
            Confirm Selection ({selectedIds.size}/{maxSelections})
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {sorted.map((book, idx) => {
          const scores = parseScores(book.scores_json);
          const isSelected = selectedIds.has(book.id);
          const isExpanded = expandedId === book.id;

          return (
            <div
              key={book.id}
              className={`rounded-lg border transition-all duration-200 ${
                isSelected
                  ? 'border-primary/50 bg-primary/[0.03] ring-1 ring-primary/20'
                  : 'border-border hover:border-border/80 hover:bg-muted/30'
              }`}
            >
              {/* ── Compact Row ────────────────────────────────── */}
              <div
                className="flex items-center gap-3 px-4 py-3 cursor-pointer"
                onClick={() => toggleBook(book.id)}
              >
                {/* Checkbox */}
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleBook(book.id)}
                  disabled={!isSelected && selectedIds.size >= maxSelections}
                  className="h-4 w-4 rounded border-gray-300 accent-primary shrink-0"
                />

                {/* Rank */}
                <div className="shrink-0 w-6 flex justify-center">
                  {rankIcon(idx)}
                </div>

                {/* Title + Authors */}
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-sm truncate">{book.title}</p>
                  <p className="text-xs text-muted-foreground truncate">
                    {book.authors ?? 'Unknown author'}
                    {book.year ? ` · ${book.year}` : ''}
                    {book.publisher ? ` · ${book.publisher}` : ''}
                  </p>
                </div>

                {/* Final Score Badge */}
                <div className="shrink-0 flex items-center gap-2">
                  {book.s_final != null && (
                    <TooltipProvider delayDuration={200}>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge
                            variant={badgeVariant(book.s_final)}
                            className="tabular-nums text-sm px-2.5 py-0.5 gap-1"
                          >
                            <Star className="h-3 w-3" />
                            {(book.s_final * 100).toFixed(0)}%
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent side="left" className="text-xs">
                          Composite score: {book.s_final.toFixed(4)}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                  )}

                  {/* Expand toggle */}
                  {scores && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 shrink-0"
                      onClick={(e) => toggleExpand(book.id, e)}
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                    </Button>
                  )}
                </div>
              </div>

              {/* ── Expanded Detail Panel ──────────────────────── */}
              {isExpanded && scores && (
                <div className="px-4 pb-4">
                  <Separator className="mb-4" />

                  {/* Score Breakdown Grid */}
                  <div className="space-y-3">
                    {/* Header row */}
                    <div className="grid grid-cols-[1fr_5rem_4.5rem_4.5rem_5rem] gap-2 text-[11px] font-medium text-muted-foreground uppercase tracking-wider px-1">
                      <span>Criterion</span>
                      <span className="text-right">Score</span>
                      <span className="text-center">×</span>
                      <span className="text-center">Weight</span>
                      <span className="text-right">Contribution</span>
                    </div>

                    {SCORE_CRITERIA
                      .filter((criterion) => criterion.key !== 'C_prac' || weights.W_prac > 0)
                      .map((criterion) => {
                      const rawScore = scores[
                        criterion.key
                      ] as number;
                      const rationale = scores[
                        criterion.rationaleKey
                      ] as string;
                      const weight = weights[criterion.weightKey] ?? 0;
                      const contribution = rawScore * weight;

                      return (
                        <Fragment key={criterion.key}>
                          <ScoreRow
                            label={criterion.label}
                            description={criterion.description}
                            score={rawScore}
                            weight={weight}
                            contribution={contribution}
                            rationale={rationale}
                          />
                        </Fragment>
                      );
                    })}

                    {/* Final Score Summary */}
                    <Separator />
                    <div className="flex items-center justify-between px-1 pt-1">
                      <span className="text-sm font-semibold">
                        Final Composite Score
                      </span>
                      <div className="flex items-center gap-3">
                        <span
                          className={`text-lg font-bold tabular-nums ${scoreColor(scores.S_final)}`}
                        >
                          {(scores.S_final * 100).toFixed(1)}%
                        </span>
                        <Badge variant={badgeVariant(scores.S_final)} className="tabular-nums">
                          {scores.S_final.toFixed(4)}
                        </Badge>
                      </div>
                    </div>

                    {weights.W_prac > 0 &&
                      scores.S_final_with_prac !== scores.S_final && (
                        <div className="flex items-center justify-between px-1 text-sm text-muted-foreground">
                          <span>
                            With Practicality (W<sub>prac</sub> ={' '}
                            {weights.W_prac.toFixed(2)})
                          </span>
                          <Badge variant="outline" className="tabular-nums">
                            {scores.S_final_with_prac.toFixed(4)}
                          </Badge>
                        </div>
                      )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {books.length === 0 && (
          <div className="text-center py-12">
            <BookOpen className="h-8 w-8 mx-auto text-muted-foreground/50 mb-3" />
            <p className="text-muted-foreground">No books found yet.</p>
            {onRediscover && (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={onRediscover}
                disabled={isRediscovering}
              >
                <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${isRediscovering ? 'animate-spin' : ''}`} />
                {isRediscovering ? 'Re-discovering…' : 'Re-discover Books'}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Score Row Component ────────────────────────────────────────

function ScoreRow({
  label,
  description,
  score,
  weight,
  contribution,
  rationale,
}: {
  label: string;
  description: string;
  score: number;
  weight: number;
  contribution: number;
  rationale: string;
}) {
  return (
    <div className="rounded-md border border-border/50 bg-muted/20 p-3 space-y-2">
      {/* Metric Row */}
      <div className="grid grid-cols-[1fr_5rem_4.5rem_4.5rem_5rem] gap-2 items-center">
        {/* Label + Description */}
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-sm font-medium cursor-help truncate">
                {label}
              </span>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs max-w-[200px]">
              {description}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>

        {/* Score */}
        <div className="text-right">
          <span className={`text-sm font-semibold tabular-nums ${scoreColor(score)}`}>
            {score.toFixed(2)}
          </span>
        </div>

        {/* Multiply sign */}
        <span className="text-center text-muted-foreground text-xs">×</span>

        {/* Weight */}
        <span className="text-center text-sm tabular-nums text-muted-foreground">
          {weight.toFixed(2)}
        </span>

        {/* Contribution */}
        <div className="text-right">
          <Badge
            variant="outline"
            className="tabular-nums text-xs font-medium"
          >
            {contribution.toFixed(3)}
          </Badge>
        </div>
      </div>

      {/* Progress bar */}
      <Progress
        value={score * 100}
        className="h-1.5"
      />

      {/* Rationale */}
      {rationale && (
        <p className="text-xs text-muted-foreground leading-relaxed pl-0.5">
          {rationale}
        </p>
      )}
    </div>
  );
}
