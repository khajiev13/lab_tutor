import { useMemo } from 'react';
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from 'recharts';

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
import { Progress } from '@/components/ui/progress';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { useChapterAnalysis } from './context';

const RADAR_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
];

// ── Component ──────────────────────────────────────────────────

export function TopicsTab() {
  const { state } = useChapterAnalysis();
  const { summaries, selectedBookId } = state;

  const summary = summaries.find(
    (s) => s.selected_book_id === selectedBookId,
  );

  // Build per-topic radar for all books
  const allTopics = useMemo(() => {
    const topicSet = new Set<string>();
    for (const s of summaries) {
      for (const t of Object.keys(s.topic_scores)) topicSet.add(t);
    }
    return [...topicSet].sort();
  }, [summaries]);

  const radarData = useMemo(
    () =>
      allTopics.map((topic) => {
        const point: Record<string, string | number> = { topic };
        for (const s of summaries) {
          point[s.book_title] = Math.round(
            (s.topic_scores[topic] ?? 0) * 100,
          );
        }
        return point;
      }),
    [allTopics, summaries],
  );

  const chartConfig: ChartConfig = {};
  for (let i = 0; i < summaries.length; i++) {
    chartConfig[summaries[i].book_title] = {
      label: summaries[i].book_title,
      color: RADAR_COLORS[i % RADAR_COLORS.length],
    };
  }

  // Topic scores for selected book
  const topicRows = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.topic_scores)
      .map(([topic, score]) => ({ topic, score }))
      .sort((a, b) => b.score - a.score);
  }, [summary]);

  // Gap matrix: topics x books
  const gapMatrix = useMemo(() => {
    return allTopics.map((topic) => {
      const row: Record<string, string | number> = { topic };
      for (const s of summaries) {
        row[s.book_title] = s.topic_scores[topic] ?? 0;
      }
      return row;
    });
  }, [allTopics, summaries]);

  if (!summary) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a book from the Overview tab to view topic details.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Radar: all books, all topics */}
      {allTopics.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Topic Coverage — All Books
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ChartContainer config={chartConfig} className="mx-auto h-[400px]">
              <RadarChart data={radarData}>
                <PolarGrid />
                <PolarAngleAxis
                  dataKey="topic"
                  tick={{ fontSize: 10 }}
                />
                <PolarRadiusAxis
                  angle={30}
                  domain={[0, 100]}
                  tick={{ fontSize: 10 }}
                />
                {summaries.map((s, i) => (
                  <Radar
                    key={s.selected_book_id}
                    name={s.book_title}
                    dataKey={s.book_title}
                    stroke={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fill={RADAR_COLORS[i % RADAR_COLORS.length]}
                    fillOpacity={
                      s.selected_book_id === selectedBookId ? 0.25 : 0.08
                    }
                    strokeWidth={
                      s.selected_book_id === selectedBookId ? 2 : 1
                    }
                  />
                ))}
                <ChartTooltip content={<ChartTooltipContent />} />
                <ChartLegend content={<ChartLegendContent />} />
              </RadarChart>
            </ChartContainer>
          </CardContent>
        </Card>
      )}

      {/* Selected book topic bars */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Topic Scores — {summary.book_title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {topicRows.map((row) => (
              <div key={row.topic} className="flex items-center gap-3">
                <span className="text-sm w-40 truncate" title={row.topic}>
                  {row.topic}
                </span>
                <Progress value={row.score * 100} className="h-2 flex-1" />
                <Badge variant="outline" className="tabular-nums text-xs w-12 justify-center">
                  {(row.score * 100).toFixed(0)}%
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Gap Matrix */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Gap Matrix</CardTitle>
          <p className="text-sm text-muted-foreground">
            Topic scores across all books — identify which books fill gaps.
          </p>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="sticky left-0 bg-background">
                  Topic
                </TableHead>
                {summaries.map((s) => (
                  <TableHead
                    key={s.selected_book_id}
                    className="text-center min-w-[80px]"
                  >
                    {s.book_title.length > 15
                      ? s.book_title.slice(0, 12) + '…'
                      : s.book_title}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {gapMatrix.map((row) => (
                <TableRow key={row.topic as string}>
                  <TableCell className="font-medium sticky left-0 bg-background">
                    {row.topic as string}
                  </TableCell>
                  {summaries.map((s) => {
                    const val = row[s.book_title] as number;
                    return (
                      <TableCell
                        key={s.selected_book_id}
                        className="text-center tabular-nums"
                        style={{
                          backgroundColor: `hsl(142 ${Math.round(val * 70)}% ${95 - Math.round(val * 30)}%)`,
                        }}
                      >
                        {(val * 100).toFixed(0)}
                      </TableCell>
                    );
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
