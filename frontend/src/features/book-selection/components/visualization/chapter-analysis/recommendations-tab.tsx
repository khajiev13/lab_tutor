import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  FileText,
  Lightbulb,
  Loader2,
  Sparkles,
} from 'lucide-react';
import { useDeferredValue, useMemo } from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
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
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

import { extractStreamingRecommendations } from '../../../lib/parse-partial-json';
import type {
  PartialRecommendationItem,
  RecommendationCategory,
  RecommendationItem,
  RecommendationPriority,
  RecommendationStreamEvent,
} from '../../../types';
import { useChapterAnalysis } from './context';

// ── Display helpers ────────────────────────────────────────────

const PRIORITY_CONFIG: Record<
  RecommendationPriority,
  { label: string; variant: 'destructive' | 'default' | 'secondary' | 'outline' }
> = {
  high: { label: 'High', variant: 'destructive' },
  medium: { label: 'Medium', variant: 'default' },
  low: { label: 'Low', variant: 'secondary' },
};

const CATEGORY_CONFIG: Record<
  RecommendationCategory,
  { label: string; icon: typeof AlertTriangle }
> = {
  missing_concept: { label: 'Missing Concept', icon: AlertTriangle },
  insufficient_coverage: { label: 'Insufficient Coverage', icon: BookOpen },
  suggested_skill: { label: 'Suggested Skill', icon: Lightbulb },
  structural: { label: 'Structural', icon: FileText },
};

function priorityOrder(p: RecommendationPriority): number {
  return p === 'high' ? 0 : p === 'medium' ? 1 : 2;
}

// ── SSE progress display ───────────────────────────────────────

function RecommendationProgress({
  events,
}: {
  events: RecommendationStreamEvent[];
}) {
  return (
    <div className="space-y-2 text-sm">
      {events.map((evt, i) => (
        <div key={i} className="flex items-center gap-2">
          {evt.type === 'done' ? (
            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
          ) : evt.type === 'error' ? (
            <AlertTriangle className="h-4 w-4 text-destructive shrink-0" />
          ) : evt.type === 'analyzing' ? (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground shrink-0" />
          ) : (
            <Sparkles className="h-4 w-4 text-muted-foreground shrink-0" />
          )}
          <span
            className={cn(
              'text-muted-foreground',
              evt.type === 'error' && 'text-destructive',
            )}
          >
            {evt.type === 'started' &&
              `Gathered ${evt.novel_count} novel + ${evt.overlap_count} overlap concepts, ${evt.teacher_doc_count} teacher docs`}
            {evt.type === 'analyzing' && evt.message}
            {evt.type === 'report' &&
              `Generated ${evt.recommendations.length} recommendations`}
            {evt.type === 'done' &&
              `Done — ${evt.total_recommendations} recommendation(s) across ${evt.total_reports} report(s)`}
            {evt.type === 'error' && evt.message}
          </span>
        </div>
      ))}
    </div>
  );
}

// ── Single recommendation card ─────────────────────────────────

function RecommendationCard({ item }: { item: RecommendationItem }) {
  const priority = PRIORITY_CONFIG[item.priority];
  const category = CATEGORY_CONFIG[item.category];
  const CategoryIcon = category.icon;

  return (
    <AccordionItem value={item.title} className="border rounded-lg px-2">
      <AccordionTrigger className="hover:no-underline py-3">
        <div className="flex items-center gap-3 text-left min-w-0">
          <CategoryIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="font-medium leading-tight line-clamp-1">
              {item.title}
            </p>
            <div className="flex items-center gap-2 mt-1">
              <Badge variant={priority.variant} className="text-xs px-1.5 py-0">
                {priority.label}
              </Badge>
              <Badge variant="outline" className="text-xs px-1.5 py-0">
                {category.label}
              </Badge>
            </div>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="space-y-3 pb-4">
        <p className="text-sm">{item.description}</p>

        <div className="space-y-2">
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Rationale
            </span>
            <p className="text-sm mt-0.5">{item.rationale}</p>
          </div>

          {item.suggested_action && (
            <div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Suggested Action
              </span>
              <p className="text-sm mt-0.5">{item.suggested_action}</p>
            </div>
          )}

          {item.affected_teacher_document && (
            <div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Affected Document
              </span>
              <p className="text-sm mt-0.5 flex items-center gap-1.5">
                <FileText className="h-3.5 w-3.5" />
                {item.affected_teacher_document}
              </p>
            </div>
          )}

          {item.book_evidence && (
            <div>
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                Book Evidence
              </span>
              <div className="mt-0.5 text-sm space-y-0.5">
                {item.book_evidence.chapter_title && (
                  <p>
                    <span className="text-muted-foreground">Chapter:</span>{' '}
                    {item.book_evidence.chapter_title}
                  </p>
                )}
                {item.book_evidence.section_title && (
                  <p>
                    <span className="text-muted-foreground">Section:</span>{' '}
                    {item.book_evidence.section_title}
                  </p>
                )}
                {item.book_evidence.text_evidence && (
                  <blockquote className="mt-1 border-l-2 pl-3 text-muted-foreground italic text-xs">
                    {item.book_evidence.text_evidence}
                  </blockquote>
                )}
              </div>
            </div>
          )}
        </div>
      </AccordionContent>
    </AccordionItem>
  );
}

// ── Streaming recommendation card (partial data) ──────────────

function StreamingRecommendationCard({
  item,
  isLast,
}: {
  item: PartialRecommendationItem;
  isLast: boolean;
}) {
  const priority =
    item.priority && item.priority in PRIORITY_CONFIG
      ? PRIORITY_CONFIG[item.priority as RecommendationPriority]
      : null;
  const category =
    item.category && item.category in CATEGORY_CONFIG
      ? CATEGORY_CONFIG[item.category as RecommendationCategory]
      : null;
  const CategoryIcon = category?.icon ?? Sparkles;

  const cursor = isLast ? (
    <span className="animate-pulse text-primary ml-0.5">▌</span>
  ) : null;

  // Determine which field is actively streaming (last non-empty in JSON order)
  let activeField = 'title';
  if (item.description) activeField = 'description';
  if (item.rationale) activeField = 'rationale';
  if (item.book_evidence) activeField = 'book_evidence';
  if (item.affected_teacher_document) activeField = 'affected_doc';
  if (item.suggested_action) activeField = 'suggested_action';

  const hasEvidence =
    item.book_evidence &&
    (item.book_evidence.chapter_title ||
      item.book_evidence.section_title ||
      item.book_evidence.text_evidence);

  return (
    <Card
      className={cn(
        'border rounded-lg',
        isLast && 'border-primary/20 shadow-sm',
      )}
    >
      <CardContent className="py-3 space-y-3">
        <div className="flex items-center gap-3 min-w-0">
          <CategoryIcon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="font-medium leading-tight">
              {item.title}
              {activeField === 'title' && cursor}
            </p>
            {(priority || category) && (
              <div className="flex items-center gap-2 mt-1">
                {priority && (
                  <Badge
                    variant={priority.variant}
                    className="text-xs px-1.5 py-0"
                  >
                    {priority.label}
                  </Badge>
                )}
                {category && (
                  <Badge variant="outline" className="text-xs px-1.5 py-0">
                    {category.label}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>

        {item.description && (
          <p className="text-sm">
            {item.description}
            {activeField === 'description' && cursor}
          </p>
        )}

        {item.rationale && (
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Rationale
            </span>
            <p className="text-sm mt-0.5">
              {item.rationale}
              {activeField === 'rationale' && cursor}
            </p>
          </div>
        )}

        {item.suggested_action && (
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Suggested Action
            </span>
            <p className="text-sm mt-0.5">
              {item.suggested_action}
              {activeField === 'suggested_action' && cursor}
            </p>
          </div>
        )}

        {item.affected_teacher_document && (
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Affected Document
            </span>
            <p className="text-sm mt-0.5 flex items-center gap-1.5">
              <FileText className="h-3.5 w-3.5" />
              {item.affected_teacher_document}
              {activeField === 'affected_doc' && cursor}
            </p>
          </div>
        )}

        {hasEvidence && (
          <div>
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Book Evidence
            </span>
            <div className="mt-0.5 text-sm space-y-0.5">
              {item.book_evidence!.chapter_title && (
                <p>
                  <span className="text-muted-foreground">Chapter:</span>{' '}
                  {item.book_evidence!.chapter_title}
                </p>
              )}
              {item.book_evidence!.section_title && (
                <p>
                  <span className="text-muted-foreground">Section:</span>{' '}
                  {item.book_evidence!.section_title}
                </p>
              )}
              {item.book_evidence!.text_evidence && (
                <blockquote className="mt-1 border-l-2 pl-3 text-muted-foreground italic text-xs">
                  {item.book_evidence!.text_evidence}
                  {activeField === 'book_evidence' && cursor}
                </blockquote>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Main tab ───────────────────────────────────────────────────

export function RecommendationsTab() {
  const { state, actions } = useChapterAnalysis();
  const {
    scores,
    selectedBookId,
    isGeneratingRecommendations,
    recommendations,
    recommendationSummary,
    recommendationBookTitle,
    recommendationEvents,
    streamingText,
  } = state;

  const selectedScore =
    scores.find((s) => s.bookId === selectedBookId) ?? null;

  // rerender-memo + js-combine-iterations: memoize derived state, single pass
  const { sorted, highCount, mediumCount, lowCount } = useMemo(() => {
    const s = [...recommendations].sort(
      (a, b) => priorityOrder(a.priority) - priorityOrder(b.priority),
    );
    let high = 0;
    let medium = 0;
    let low = 0;
    for (const r of s) {
      if (r.priority === 'high') high++;
      else if (r.priority === 'medium') medium++;
      else low++;
    }
    return { sorted: s, highCount: high, mediumCount: medium, lowCount: low };
  }, [recommendations]);

  // Defer the high-frequency streamingText so the expensive parse +
  // card rendering only runs when React has idle time, preventing
  // layout shifts and scroll jumps on every token.
  const deferredStreamingText = useDeferredValue(streamingText);
  const streamingParsed = useMemo(
    () =>
      deferredStreamingText
        ? extractStreamingRecommendations(deferredStreamingText)
        : null,
    [deferredStreamingText],
  );

  return (
    <div className="space-y-6">
      {/* Generate button */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Sparkles className="h-4.5 w-4.5" />
            Content Recommendations
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Uses AI to analyze gaps between the selected book and your uploaded
            course materials, then generates actionable recommendations.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {recommendations.length === 0 && !isGeneratingRecommendations ? (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button disabled={!selectedBookId}>
                  <Sparkles className="mr-2 h-4 w-4" />
                  Generate Recommendations
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>
                    Generate Content Recommendations?
                  </AlertDialogTitle>
                  <AlertDialogDescription>
                    This will analyze the gaps between the book and your teacher
                    materials using an LLM. The process may take 30–60 seconds.
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
                      if (selectedBookId) {
                        actions.generateRecommendations(selectedBookId);
                      }
                    }}
                  >
                    Generate
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          ) : isGeneratingRecommendations ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Generating recommendations…
            </div>
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={!selectedBookId || isGeneratingRecommendations}
              onClick={() => {
                if (selectedBookId) {
                  actions.generateRecommendations(selectedBookId);
                }
              }}
            >
              <Sparkles className="mr-2 h-3.5 w-3.5" />
              Regenerate
            </Button>
          )}

          {/* SSE progress — hide once final results are displayed */}
          {recommendationEvents.length > 0 &&
            (isGeneratingRecommendations || recommendations.length === 0) && (
            <>
              <Separator />
              <RecommendationProgress events={recommendationEvents} />
            </>
          )}
        </CardContent>
      </Card>

      {/* Progressive streaming cards */}
      {streamingParsed && (
        <>
          {streamingParsed.summary && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {selectedScore?.bookTitle
                    ? `Generating for "${selectedScore.bookTitle}"…`
                    : 'Generating Recommendations…'}
                </CardTitle>
                <p className="text-sm text-muted-foreground">
                  {streamingParsed.summary}
                  {streamingParsed.items.length === 0 && (
                    <span className="animate-pulse text-primary ml-0.5">
                      ▌
                    </span>
                  )}
                </p>
              </CardHeader>
            </Card>
          )}

          {streamingParsed.items.map((item, i) => (
            <StreamingRecommendationCard
              key={item.title || `streaming-${i}`}
              item={item}
              isLast={i === streamingParsed.items.length - 1}
            />
          ))}
        </>
      )}

      {/* Final results (after streaming completes) */}
      {!streamingText && recommendations.length > 0 && (
        <>
          {/* Summary */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">
                {recommendationBookTitle
                  ? `Recommendations for "${recommendationBookTitle}"`
                  : 'Recommendations'}
              </CardTitle>
              {recommendationSummary && (
                <p className="text-sm text-muted-foreground">
                  {recommendationSummary}
                </p>
              )}
            </CardHeader>
            <CardContent>
              <div className="flex gap-3">
                {highCount > 0 && (
                  <Badge variant="destructive">
                    {highCount} High Priority
                  </Badge>
                )}
                {mediumCount > 0 && (
                  <Badge variant="default">
                    {mediumCount} Medium
                  </Badge>
                )}
                {lowCount > 0 && (
                  <Badge variant="secondary">
                    {lowCount} Low
                  </Badge>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Recommendation list */}
          <Accordion type="multiple" className="space-y-2">
            {sorted.map((item) => (
              <RecommendationCard key={item.title} item={item} />
            ))}
          </Accordion>
        </>
      )}
    </div>
  );
}
