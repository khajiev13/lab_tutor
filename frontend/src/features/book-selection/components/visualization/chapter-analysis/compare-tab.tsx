import { useMemo, useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type { ChapterAnalysisSummary } from '../../../types';
import { useChapterAnalysis } from './context';

// ── Component ──────────────────────────────────────────────────

export function CompareTab() {
  const { state } = useChapterAnalysis();
  const { summaries, scores } = state;

  const [bookAId, setBookAId] = useState<number | null>(
    summaries[0]?.selected_book_id ?? null,
  );
  const [bookBId, setBookBId] = useState<number | null>(
    summaries[1]?.selected_book_id ?? null,
  );

  const bookA = summaries.find((s) => s.selected_book_id === bookAId);
  const bookB = summaries.find((s) => s.selected_book_id === bookBId);
  const scoreA = scores.find((s) => s.bookId === bookAId);
  const scoreB = scores.find((s) => s.bookId === bookBId);

  // Merge all course concepts from both books
  const mergedConcepts = useMemo(() => {
    const map = new Map<
      string,
      { name: string; topic: string; simA: number; matchA: string; simB: number; matchB: string }
    >();

    const addCoverage = (
      s: ChapterAnalysisSummary | undefined,
      side: 'A' | 'B',
    ) => {
      if (!s) return;
      for (const c of s.course_coverage) {
        let entry = map.get(c.concept_name);
        if (!entry) {
          entry = {
            name: c.concept_name,
            topic: c.doc_topic,
            simA: 0,
            matchA: '',
            simB: 0,
            matchB: '',
          };
          map.set(c.concept_name, entry);
        }
        if (side === 'A') {
          entry.simA = c.sim_max;
          entry.matchA = c.best_match;
        } else {
          entry.simB = c.sim_max;
          entry.matchB = c.best_match;
        }
      }
    };

    addCoverage(bookA, 'A');
    addCoverage(bookB, 'B');
    return [...map.values()].sort((a, b) =>
      Math.abs(b.simA - b.simB) - Math.abs(a.simA - a.simB) !== 0
        ? Math.abs(b.simA - b.simB) - Math.abs(a.simA - a.simB)
        : b.simA + b.simB - (a.simA + a.simB),
    );
  }, [bookA, bookB]);

  if (summaries.length < 2) {
    return (
      <p className="text-sm text-muted-foreground">
        At least two books are needed for comparison.
      </p>
    );
  }

  const METRICS: { label: string; getA: () => string; getB: () => string }[] = [
    {
      label: 'Composite Score',
      getA: () => scoreA ? (scoreA.composite * 100).toFixed(0) : '—',
      getB: () => scoreB ? (scoreB.composite * 100).toFixed(0) : '—',
    },
    {
      label: 'Total Chapters',
      getA: () => String(bookA?.total_chapters ?? '—'),
      getB: () => String(bookB?.total_chapters ?? '—'),
    },
    {
      label: 'Core Concepts',
      getA: () => String(bookA?.total_core_concepts ?? '—'),
      getB: () => String(bookB?.total_core_concepts ?? '—'),
    },
    {
      label: 'Supplementary',
      getA: () => String(bookA?.total_supplementary_concepts ?? '—'),
      getB: () => String(bookB?.total_supplementary_concepts ?? '—'),
    },
    {
      label: 'Skills',
      getA: () => String(bookA?.total_skills ?? '—'),
      getB: () => String(bookB?.total_skills ?? '—'),
    },
    {
      label: 'Novel Concepts',
      getA: () => String(bookA?.novel_count_default ?? '—'),
      getB: () => String(bookB?.novel_count_default ?? '—'),
    },
    {
      label: 'Covered Concepts',
      getA: () => String(bookA?.covered_count_default ?? '—'),
      getB: () => String(bookB?.covered_count_default ?? '—'),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Book Selectors */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-sm font-medium">Book A</label>
          <Select
            value={bookAId ? String(bookAId) : undefined}
            onValueChange={(v) => setBookAId(Number(v))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select book A" />
            </SelectTrigger>
            <SelectContent>
              {summaries.map((s) => (
                <SelectItem
                  key={s.selected_book_id}
                  value={String(s.selected_book_id)}
                >
                  {s.book_title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <label className="text-sm font-medium">Book B</label>
          <Select
            value={bookBId ? String(bookBId) : undefined}
            onValueChange={(v) => setBookBId(Number(v))}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select book B" />
            </SelectTrigger>
            <SelectContent>
              {summaries.map((s) => (
                <SelectItem
                  key={s.selected_book_id}
                  value={String(s.selected_book_id)}
                >
                  {s.book_title}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Score Factor Comparison */}
      {scoreA && scoreB && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Factor Comparison</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {(
                [
                  'coverage',
                  'depth',
                  'novelty',
                  'balance',
                  'skillRichness',
                  'density',
                ] as const
              ).map((factor) => (
                <div key={factor} className="space-y-1">
                  <div className="flex justify-between text-sm">
                    <span className="capitalize">{factor}</span>
                    <span className="tabular-nums text-xs text-muted-foreground">
                      {(scoreA.factors[factor] * 100).toFixed(0)} vs{' '}
                      {(scoreB.factors[factor] * 100).toFixed(0)}
                    </span>
                  </div>
                  <div className="flex gap-1 h-2">
                    <Progress
                      value={scoreA.factors[factor] * 100}
                      className="h-2 flex-1"
                    />
                    <Progress
                      value={scoreB.factors[factor] * 100}
                      className="h-2 flex-1"
                    />
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Side-by-side Metrics */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Key Metrics</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Metric</TableHead>
                <TableHead className="text-center">
                  {bookA?.book_title
                    ? bookA.book_title.slice(0, 20)
                    : 'Book A'}
                </TableHead>
                <TableHead className="text-center">
                  {bookB?.book_title
                    ? bookB.book_title.slice(0, 20)
                    : 'Book B'}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {METRICS.map((m) => (
                <TableRow key={m.label}>
                  <TableCell className="font-medium">{m.label}</TableCell>
                  <TableCell className="text-center tabular-nums">
                    {m.getA()}
                  </TableCell>
                  <TableCell className="text-center tabular-nums">
                    {m.getB()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Per-concept Comparison */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Course Concept Coverage Comparison
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Sorted by largest difference in similarity between the two books.
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Concept</TableHead>
                <TableHead>Topic</TableHead>
                <TableHead className="text-center">A Sim %</TableHead>
                <TableHead className="text-center">B Sim %</TableHead>
                <TableHead className="text-center">Diff</TableHead>
                <TableHead className="text-center">Winner</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mergedConcepts.slice(0, 100).map((c) => {
                const diff = c.simA - c.simB;
                return (
                  <TableRow key={c.name}>
                    <TableCell className="font-medium">{c.name}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {c.topic}
                    </TableCell>
                    <TableCell className="text-center tabular-nums">
                      {(c.simA * 100).toFixed(0)}
                    </TableCell>
                    <TableCell className="text-center tabular-nums">
                      {(c.simB * 100).toFixed(0)}
                    </TableCell>
                    <TableCell className="text-center tabular-nums">
                      {diff > 0 ? '+' : ''}
                      {(diff * 100).toFixed(0)}
                    </TableCell>
                    <TableCell className="text-center">
                      {Math.abs(diff) < 0.05 ? (
                        <Badge variant="outline" className="text-xs">
                          Tie
                        </Badge>
                      ) : diff > 0 ? (
                        <Badge className="text-xs">A</Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs">
                          B
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
