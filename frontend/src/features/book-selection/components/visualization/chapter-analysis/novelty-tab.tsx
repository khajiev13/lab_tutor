import { useMemo, useState } from 'react';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { Slider } from '@/components/ui/slider';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type { ChapterDetail, SectionConceptItem } from '../../../types';
import { useChapterAnalysis } from './context';

// ── Component ──────────────────────────────────────────────────

export function NoveltyTab() {
  const { state } = useChapterAnalysis();
  const { summaries, selectedBookId, novelThreshold, coveredThreshold } = state;
  const [localNovel, setLocalNovel] = useState(novelThreshold);

  const summary = summaries.find(
    (s) => s.selected_book_id === selectedBookId,
  );

  // Stacked bar data: per-book novel / overlap / covered
  const stackedData = useMemo(
    () =>
      summaries.map((s) => {
        // Recompute with local thresholds
        let novel = 0,
          overlap = 0,
          covered = 0;
        for (const c of s.book_unique_concepts) {
          if (c.sim_max < localNovel) novel++;
          else if (c.sim_max >= coveredThreshold) covered++;
          else overlap++;
        }
        return {
          book: s.book_title.length > 25
            ? s.book_title.slice(0, 22) + '…'
            : s.book_title,
          full_title: s.book_title,
          Novel: novel,
          Overlap: overlap,
          Covered: covered,
        };
      }),
    [summaries, localNovel, coveredThreshold],
  );

  const chartConfig: ChartConfig = {
    Novel: { label: 'Novel', color: 'var(--chart-3)' },
    Overlap: { label: 'Overlap', color: 'var(--chart-4)' },
    Covered: { label: 'Covered', color: 'var(--chart-2)' },
  };

  // Per-chapter drill-down for selected book
  const chapterNovelty = useMemo(() => {
    if (!summary) return [];
    return summary.chapter_details.map((ch) => {
      let novel = 0,
        total = 0;
      for (const sec of ch.sections) {
        for (const c of sec.concepts) {
          total++;
          if (c.sim_max !== null && c.sim_max < localNovel) novel++;
          else if (c.sim_max === null) novel++;
        }
      }
      return {
        chapter: ch.chapter_title,
        chapterIndex: ch.chapter_index,
        novel,
        total,
        ratio: total > 0 ? novel / total : 0,
      };
    });
  }, [summary, localNovel]);

  if (!summary) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a book from the Overview tab to view novelty details.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Threshold */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Novelty Threshold</CardTitle>
          <p className="text-sm text-muted-foreground">
            Concepts with similarity below this value are counted as novel
            (unique to the book, not in your course).
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <Slider
              min={0}
              max={100}
              step={5}
              value={[localNovel * 100]}
              onValueChange={([v]) => setLocalNovel(v / 100)}
              className="flex-1"
            />
            <span className="text-sm tabular-nums w-12 text-right">
              {(localNovel * 100).toFixed(0)}%
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Stacked Bar: all books */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Book Concept Breakdown
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="h-[300px]">
            <BarChart
              data={stackedData}
              margin={{ left: 10, right: 10, top: 10, bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="book"
                tick={{ fontSize: 10 }}
                interval={0}
                angle={-20}
                textAnchor="end"
                height={60}
              />
              <YAxis />
              <Bar dataKey="Novel" stackId="a" fill="var(--chart-3)" radius={[0, 0, 0, 0]} />
              <Bar dataKey="Overlap" stackId="a" fill="var(--chart-4)" />
              <Bar dataKey="Covered" stackId="a" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      {/* Per-chapter novelty for selected book */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Chapter-level Novelty — {summary.book_title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Accordion type="multiple" className="w-full">
            {chapterNovelty.map((ch) => (
              <AccordionItem
                key={ch.chapterIndex}
                value={String(ch.chapterIndex)}
              >
                <AccordionTrigger className="text-sm">
                  <span className="flex items-center gap-2">
                    <Badge variant="outline" className="tabular-nums">
                      {ch.novel}/{ch.total}
                    </Badge>
                    {ch.chapter}
                    <span className="text-xs text-muted-foreground ml-auto">
                      {(ch.ratio * 100).toFixed(0)}% novel
                    </span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <NovelConceptsTable
                    chapterIndex={ch.chapterIndex}
                    chapterDetails={summary.chapter_details}
                    novelThreshold={localNovel}
                  />
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────

/**
 * Highlight all occurrences of `term` inside `text` by wrapping them in <mark>.
 * Uses a case-insensitive, word-boundary-aware search.
 */
function HighlightedEvidence({
  text,
  term,
}: {
  text: string;
  term: string;
}) {
  if (!text || !term) return <span>{text}</span>;

  // Escape regex special chars in the concept name
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${escaped})`, 'gi');
  const parts = text.split(regex);

  return (
    <span>
      {parts.map((part, i) =>
        regex.test(part) ? (
          <mark
            key={i}
            className="bg-yellow-200/80 dark:bg-yellow-500/30 text-foreground rounded-sm px-0.5"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        ),
      )}
    </span>
  );
}

// ── Sub-component ──────────────────────────────────────────────

function NovelConceptsTable({
  chapterIndex,
  chapterDetails,
  novelThreshold,
}: {
  chapterIndex: number;
  chapterDetails: ChapterDetail[];
  novelThreshold: number;
}) {
  const chapter = chapterDetails.find(
    (c) => c.chapter_index === chapterIndex,
  );
  if (!chapter) return null;

  const concepts = chapter.sections.flatMap((sec) =>
    sec.concepts.map((c) => ({ ...c, section: sec.section_title })),
  );

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Concept</TableHead>
          <TableHead>Section</TableHead>
          <TableHead className="w-[80px] text-center">Sim %</TableHead>
          <TableHead className="w-[80px] text-center">Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {concepts
          .sort((a, b) => (a.sim_max ?? 0) - (b.sim_max ?? 0))
          .map((c) => {
            const sim = c.sim_max ?? 0;
            const isNovel = sim < novelThreshold;
            return (
              <TableRow key={`${c.section}-${c.name}`}>
                <TableCell className="font-medium p-0">
                  <ConceptHoverCard concept={c} chapterSummary={chapter.chapter_summary} />
                </TableCell>
                <TableCell className="text-xs text-muted-foreground truncate max-w-[150px]">
                  {c.section}
                </TableCell>
                <TableCell className="text-center tabular-nums">
                  {(sim * 100).toFixed(0)}
                </TableCell>
                <TableCell className="text-center">
                  <Badge
                    variant={isNovel ? 'default' : 'secondary'}
                    className="text-xs"
                  >
                    {isNovel ? 'Novel' : 'Known'}
                  </Badge>
                </TableCell>
              </TableRow>
            );
          })}
      </TableBody>
    </Table>
  );
}

// ── Concept hover card ─────────────────────────────────────────

function ConceptHoverCard({
  concept,
  chapterSummary,
}: {
  concept: SectionConceptItem & { section: string };
  chapterSummary: string | null;
}) {
  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          className="w-full text-left px-2 py-2 font-medium underline decoration-dotted decoration-muted-foreground/50 underline-offset-4 hover:decoration-primary cursor-pointer transition-colors"
        >
          {concept.name}
        </button>
      </HoverCardTrigger>
      <HoverCardContent
        side="right"
        align="start"
        className="w-[420px] max-h-[400px] overflow-y-auto space-y-3"
      >
        {/* Header */}
        <div className="space-y-1">
          <p className="text-sm font-semibold">{concept.name}</p>
          <div className="flex items-center gap-1.5">
            <Badge variant="outline" className="text-[10px] capitalize">
              {concept.relevance}
            </Badge>
            {concept.best_course_match && (
              <span className="text-[10px] text-muted-foreground">
                closest match: {concept.best_course_match}
              </span>
            )}
          </div>
        </div>

        {/* Description */}
        {concept.description && (
          <div className="space-y-1">
            <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Description
            </p>
            <p className="text-xs leading-relaxed">{concept.description}</p>
          </div>
        )}

        {/* Text Evidence with highlighting */}
        {concept.text_evidence && (
          <div className="space-y-1">
            <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Book Evidence
            </p>
            <div className="text-xs leading-relaxed rounded-md bg-muted/50 p-2.5 border border-border/50">
              <HighlightedEvidence
                text={concept.text_evidence}
                term={concept.name}
              />
            </div>
          </div>
        )}

        {/* Chapter Summary context */}
        {chapterSummary && (
          <details className="group">
            <summary className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground cursor-pointer select-none hover:text-foreground transition-colors">
              Chapter Summary
            </summary>
            <div className="mt-1 text-xs leading-relaxed rounded-md bg-muted/30 p-2.5 border border-border/30">
              <HighlightedEvidence
                text={chapterSummary}
                term={concept.name}
              />
            </div>
          </details>
        )}
      </HoverCardContent>
    </HoverCard>
  );
}
