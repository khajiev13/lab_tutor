import { useMemo, useState } from 'react';

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import type { ChapterDetail, ConceptRelevance } from '../../../types';
import { useChapterAnalysis } from './context';

// ── Helpers ────────────────────────────────────────────────────

function relevanceBadge(rel: ConceptRelevance) {
  const variants: Record<ConceptRelevance, 'default' | 'secondary' | 'outline'> = {
    core: 'default',
    supplementary: 'secondary',
    tangential: 'outline',
  };
  return (
    <Badge variant={variants[rel]} className="text-xs capitalize">
      {rel}
    </Badge>
  );
}

type SortKey = 'name' | 'relevance' | 'sim_max';

// ── Component ──────────────────────────────────────────────────

export function ChaptersTab() {
  const { state, actions } = useChapterAnalysis();
  const { summaries, selectedBookId } = state;
  const [sortKey, setSortKey] = useState<SortKey>('sim_max');

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
      {/* Book Selector + Sort */}
      <div className="flex flex-wrap gap-4 items-end">
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
        <div className="space-y-1">
          <label className="text-sm font-medium">Sort Concepts By</label>
          <Select
            value={sortKey}
            onValueChange={(v) => setSortKey(v as SortKey)}
          >
            <SelectTrigger className="w-[160px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="sim_max">Similarity</SelectItem>
              <SelectItem value="relevance">Relevance</SelectItem>
              <SelectItem value="name">Name</SelectItem>
            </SelectContent>
          </Select>
        </div>
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
            <p className="text-2xl font-bold">{summary.total_core_concepts}</p>
            <p className="text-xs text-muted-foreground">Core</p>
          </CardContent>
        </Card>
        <Card className="flex-1 min-w-[120px]">
          <CardContent className="pt-4 text-center">
            <p className="text-2xl font-bold">
              {summary.total_supplementary_concepts}
            </p>
            <p className="text-xs text-muted-foreground">Supplementary</p>
          </CardContent>
        </Card>
        <Card className="flex-1 min-w-[120px]">
          <CardContent className="pt-4 text-center">
            <p className="text-2xl font-bold">{summary.total_skills}</p>
            <p className="text-xs text-muted-foreground">Skills</p>
          </CardContent>
        </Card>
      </div>

      {/* Chapter Accordion */}
      <Accordion type="multiple" className="w-full space-y-2">
        {sortedChapters.map((ch) => (
          <ChapterCard key={ch.chapter_index} chapter={ch} sortKey={sortKey} />
        ))}
      </Accordion>
    </div>
  );
}

// ── Sub-component ──────────────────────────────────────────────

function ChapterCard({
  chapter,
  sortKey,
}: {
  chapter: ChapterDetail;
  sortKey: SortKey;
}) {
  const allConcepts = useMemo(
    () =>
      chapter.sections.flatMap((sec) =>
        sec.concepts.map((c) => ({ ...c, section: sec.section_title })),
      ),
    [chapter],
  );

  const sortedConcepts = useMemo(() => {
    const sorted = [...allConcepts];
    switch (sortKey) {
      case 'sim_max':
        sorted.sort((a, b) => (b.sim_max ?? -1) - (a.sim_max ?? -1));
        break;
      case 'relevance': {
        const order = { core: 0, supplementary: 1, tangential: 2 };
        sorted.sort(
          (a, b) =>
            order[a.relevance as ConceptRelevance] -
            order[b.relevance as ConceptRelevance],
        );
        break;
      }
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name));
        break;
    }
    return sorted;
  }, [allConcepts, sortKey]);

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
              {chapter.core_count} core
            </Badge>
            <Badge variant="secondary" className="text-xs">
              {chapter.supplementary_count} supp
            </Badge>
            {chapter.skills.length > 0 && (
              <Badge variant="outline" className="text-xs">
                {chapter.skills.length} skills
              </Badge>
            )}
          </div>
        </div>
      </AccordionTrigger>
      <AccordionContent className="space-y-4">
        {chapter.chapter_summary && (
          <p className="text-sm text-muted-foreground italic">
            {chapter.chapter_summary}
          </p>
        )}

        {/* Skills */}
        {chapter.skills.length > 0 && (
          <div>
            <h4 className="text-sm font-medium mb-2">Skills</h4>
            <div className="flex flex-wrap gap-2">
              {chapter.skills.map((skill) => (
                <Badge key={skill.name} variant="outline">
                  {skill.name}
                  {skill.concept_names.length > 0 && (
                    <span className="ml-1 text-muted-foreground">
                      ({skill.concept_names.length})
                    </span>
                  )}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Concept Table */}
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Concept</TableHead>
              <TableHead>Section</TableHead>
              <TableHead className="w-[90px]">Relevance</TableHead>
              <TableHead className="w-[80px] text-center">Sim %</TableHead>
              <TableHead className="w-[140px]">Best Match</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sortedConcepts.map((c) => (
              <TableRow key={`${c.section}-${c.name}`}>
                <TableCell className="font-medium">{c.name}</TableCell>
                <TableCell className="text-xs text-muted-foreground truncate max-w-[120px]">
                  {c.section}
                </TableCell>
                <TableCell>
                  {relevanceBadge(c.relevance as ConceptRelevance)}
                </TableCell>
                <TableCell className="text-center tabular-nums">
                  {c.sim_max !== null ? (c.sim_max * 100).toFixed(0) : '—'}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground truncate max-w-[140px]">
                  {c.best_course_match ?? '—'}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </AccordionContent>
    </AccordionItem>
  );
}
