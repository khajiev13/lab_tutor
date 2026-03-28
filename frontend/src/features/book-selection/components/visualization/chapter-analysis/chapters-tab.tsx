import { useMemo } from 'react';

import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import type { ChapterDetail } from '../../../types';
import { useChapterAnalysis } from './context';

// ── Component ──────────────────────────────────────────────────

export function ChaptersTab() {
  const { state, actions } = useChapterAnalysis();
  const { summaries, selectedBookId } = state;

  const summary = summaries.find(
    (s) => s.selected_book_id === selectedBookId,
  );

  const sortedChapters = useMemo(() => {
    if (!summary) return [];
    return [...summary.chapter_details].sort(
      (a, b) => a.chapter_index - b.chapter_index,
    );
  }, [summary]);

  if (!summary) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a book from the Overview tab to view chapter details.
      </p>
    );
  }

  return (
    <div className="space-y-6">
      {/* Book Selector */}
      <div className="space-y-1">
        <label className="text-sm font-medium">Book</label>
        <Select
          value={String(selectedBookId)}
          onValueChange={(v) => actions.setSelectedBook(Number(v))}
        >
          <SelectTrigger className="w-[300px]">
            <SelectValue />
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

      {/* Stats */}
      <div className="flex flex-wrap gap-4">
        <Card className="flex-1 min-w-[120px]">
          <CardContent className="pt-4 text-center">
            <p className="text-2xl font-bold">{summary.total_chapters}</p>
            <p className="text-xs text-muted-foreground">Chapters</p>
          </CardContent>
        </Card>
        <Card className="flex-1 min-w-[120px]">
          <CardContent className="pt-4 text-center">
            <p className="text-2xl font-bold">{summary.total_skills}</p>
            <p className="text-xs text-muted-foreground">Skills</p>
          </CardContent>
        </Card>
        <Card className="flex-1 min-w-[120px]">
          <CardContent className="pt-4 text-center">
            <p className="text-2xl font-bold">
              {summary.total_supplementary_concepts}
            </p>
            <p className="text-xs text-muted-foreground">Concepts</p>
          </CardContent>
        </Card>
      </div>

      {/* Chapter Accordion */}
      <Accordion type="multiple" className="w-full space-y-2">
        {sortedChapters.map((ch) => (
          <ChapterCard key={ch.chapter_index} chapter={ch} />
        ))}
      </Accordion>
    </div>
  );
}

// ── Sub-component ──────────────────────────────────────────────

function ChapterCard({ chapter }: { chapter: ChapterDetail }) {
  return (
    <AccordionItem value={String(chapter.chapter_index)}>
      <AccordionTrigger className="text-sm hover:no-underline">
        <div className="flex items-center gap-2 text-left">
          <Badge variant="outline" className="shrink-0 tabular-nums">
            Ch. {chapter.chapter_index + 1}
          </Badge>
          <span className="font-medium">{chapter.chapter_title}</span>
          <div className="flex gap-1 ml-auto mr-4">
            <Badge variant="default" className="text-xs">
              {chapter.skill_count} skills
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {chapter.concept_count} concepts
            </Badge>
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="space-y-3">
        {chapter.chapter_summary && (
          <p className="text-sm text-muted-foreground italic">
            {chapter.chapter_summary}
          </p>
        )}

        {chapter.skills.map((skill) => (
          <div key={skill.name} className="border rounded-md p-3 space-y-2">
            <p className="text-sm font-medium">{skill.name}</p>
            {skill.description && (
              <p className="text-xs text-muted-foreground">{skill.description}</p>
            )}
            {skill.concepts.length > 0 && (
              <div className="flex flex-wrap gap-1 pt-1">
                {skill.concepts.map((c) => (
                  <Badge
                    key={c.name}
                    variant="outline"
                    className="text-xs gap-1"
                    title={c.description || undefined}
                  >
                    {c.name}
                    {c.sim_max !== null && c.sim_max !== undefined && (
                      <span className="text-muted-foreground">
                        {(c.sim_max * 100).toFixed(0)}%
                      </span>
                    )}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        ))}
      </AccordionContent>
    </AccordionItem>
  );
}
