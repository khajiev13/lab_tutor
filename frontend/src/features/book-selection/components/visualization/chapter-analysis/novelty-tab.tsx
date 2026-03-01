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
import { Slider } from '@/components/ui/slider';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

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
                    summary={summary}
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

// ── Sub-component ──────────────────────────────────────────────

function NovelConceptsTable({
  chapterIndex,
  summary,
  novelThreshold,
}: {
  chapterIndex: number;
  summary: { chapter_details: { chapter_index: number; sections: { section_title: string; concepts: { name: string; sim_max: number | null; best_course_match: string | null; relevance: string }[] }[] }[] };
  novelThreshold: number;
}) {
  const chapter = summary.chapter_details.find(
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
                <TableCell className="font-medium">{c.name}</TableCell>
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
