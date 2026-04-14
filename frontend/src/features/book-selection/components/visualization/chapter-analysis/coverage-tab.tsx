import {
  useCallback,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  FileText,
  GraduationCap,
  Zap,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Slider } from '@/components/ui/slider';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

import type { ConceptCoverageItem } from '../../../types';
import { useChapterAnalysis } from './context';

// ── Types ──────────────────────────────────────────────────────

interface GroupedTopic {
  topic: string;
  items: ConceptCoverageItem[];
  avgSim: number;
}

// ── Helpers ────────────────────────────────────────────────────

function statusInfo(sim: number, threshold: number) {
  if (sim >= threshold)
    return {
      label: 'Covered',
      color: 'bg-emerald-500',
      text: 'text-emerald-600',
      ring: 'ring-emerald-500/20',
      bg: 'bg-emerald-50 dark:bg-emerald-950/30',
      beam: '#10b981',
    };
  if (sim >= threshold * 0.6)
    return {
      label: 'Partial',
      color: 'bg-amber-500',
      text: 'text-amber-600',
      ring: 'ring-amber-500/20',
      bg: 'bg-amber-50 dark:bg-amber-950/30',
      beam: '#f59e0b',
    };
  return {
    label: 'Gap',
    color: 'bg-red-500',
    text: 'text-red-500',
    ring: 'ring-red-500/20',
    bg: 'bg-red-50 dark:bg-red-950/30',
    beam: '#ef4444',
  };
}

function groupByTopic(items: ConceptCoverageItem[]): GroupedTopic[] {
  const map: Record<string, ConceptCoverageItem[]> = {};
  for (const item of items) {
    const topic = item.doc_topic || 'Uncategorized';
    (map[topic] ??= []).push(item);
  }
  return Object.entries(map)
    .map(([topic, items]) => ({
      topic,
      items: items.sort((a, b) => b.sim_max - a.sim_max),
      avgSim: items.reduce((s, i) => s + i.sim_max, 0) / items.length,
    }))
    .sort((a, b) => b.avgSim - a.avgSim);
}

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max) + '…' : s;
}

// ── Animated Stat Ring ─────────────────────────────────────────

function StatRing({
  covered,
  partial,
  gap,
  total,
}: {
  covered: number;
  partial: number;
  gap: number;
  total: number;
}) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const coveredPct = total ? covered / total : 0;
  const partialPct = total ? partial / total : 0;
  const gapPct = total ? gap / total : 0;

  return (
    <div className="relative w-28 h-28 flex-shrink-0">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        {/* Background ring */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth="8"
          className="text-muted/30"
        />
        {/* Gap segment */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#ef4444"
          strokeWidth="8"
          strokeDasharray={`${circumference * gapPct} ${circumference * (1 - gapPct)}`}
          strokeDashoffset={-circumference * (coveredPct + partialPct)}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
        {/* Partial segment */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#f59e0b"
          strokeWidth="8"
          strokeDasharray={`${circumference * partialPct} ${circumference * (1 - partialPct)}`}
          strokeDashoffset={-circumference * coveredPct}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
        {/* Covered segment */}
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke="#10b981"
          strokeWidth="8"
          strokeDasharray={`${circumference * coveredPct} ${circumference * (1 - coveredPct)}`}
          strokeLinecap="round"
          className="transition-all duration-1000 ease-out"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-bold tabular-nums">{total}</span>
        <span className="text-[10px] text-muted-foreground">concepts</span>
      </div>
    </div>
  );
}

// ── Evidence Panel ─────────────────────────────────────────────

function EvidencePanel({
  item,
  threshold,
}: {
  item: ConceptCoverageItem;
  threshold: number;
}) {
  const info = statusInfo(item.sim_max, threshold);

  return (
    <div
      className="grid grid-cols-[1fr_auto_1fr] gap-3 animate-in fade-in slide-in-from-top-2 duration-300"
    >
      {/* Book side */}
      <div className={`rounded-lg p-3 ${info.bg} ring-1 ${info.ring}`}>
        <div className="flex items-center gap-1.5 mb-2">
          <BookOpen className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Book
          </span>
          {item.matched_relevance && (
            <Badge
              variant={item.matched_relevance === 'core' ? 'default' : 'outline'}
              className="text-[9px] h-4 px-1"
            >
              {item.matched_relevance}
            </Badge>
          )}
        </div>
        <p className="text-xs font-medium mb-1">{item.best_match}</p>
        {item.book_chapter_title && (
          <p className="text-[10px] text-muted-foreground mb-2">
            Ch: {item.book_chapter_title}
            {item.book_section_title ? ` → ${item.book_section_title}` : ''}
          </p>
        )}
        {item.book_text_evidence ? (
          <blockquote className="text-[11px] leading-relaxed text-muted-foreground italic border-l-2 border-current pl-2 opacity-80">
            "{truncate(item.book_text_evidence, 300)}"
          </blockquote>
        ) : (
          <p className="text-[11px] text-muted-foreground/50 italic">
            No text evidence available
          </p>
        )}
      </div>

      {/* Center: similarity badge */}
      <div className="flex flex-col items-center justify-center gap-1">
        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center ring-2 ${info.ring} ${info.color} text-white text-xs font-bold shadow-md`}
        >
          {(item.sim_max * 100).toFixed(0)}
        </div>
        {item.sim_evidence != null && item.sim_evidence !== item.sim_max && (
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="text-[10px] tabular-nums text-muted-foreground">
                  ev: {(item.sim_evidence * 100).toFixed(0)}%
                </span>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                Evidence embedding similarity
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        <Zap className={`w-3 h-3 ${info.text} animate-pulse`} />
      </div>

      {/* Course side */}
      <div className={`rounded-lg p-3 ${info.bg} ring-1 ${info.ring}`}>
        <div className="flex items-center gap-1.5 mb-2">
          <GraduationCap className="w-3.5 h-3.5 text-muted-foreground" />
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
            Course
          </span>
        </div>
        <p className="text-xs font-medium mb-1">{item.concept_name}</p>
        <p className="text-[10px] text-muted-foreground mb-2">
          Topic: {item.doc_topic || 'N/A'}
        </p>
        {item.course_text_evidence ? (
          <blockquote className="text-[11px] leading-relaxed text-muted-foreground italic border-l-2 border-current pl-2 opacity-80">
            "{truncate(item.course_text_evidence, 300)}"
          </blockquote>
        ) : (
          <p className="text-[11px] text-muted-foreground/50 italic">
            No text evidence available
          </p>
        )}
      </div>
    </div>
  );
}

// ── Concept Row ────────────────────────────────────────────────

function ConceptRow({
  item,
  threshold,
  isExpanded,
  onToggle,
  onHover,
  rowRef,
}: {
  item: ConceptCoverageItem;
  threshold: number;
  isExpanded: boolean;
  onToggle: () => void;
  onHover: (hovering: boolean) => void;
  rowRef: (el: HTMLDivElement | null) => void;
}) {
  const info = statusInfo(item.sim_max, threshold);
  const simPct = Math.round(item.sim_max * 100);

  return (
    <div ref={rowRef} className="group">
      {/* Main Row */}
      <button
        onClick={onToggle}
        onMouseEnter={() => onHover(true)}
        onMouseLeave={() => onHover(false)}
        className={`
          w-full text-left grid grid-cols-[1fr_minmax(100px,auto)_60px_80px_24px]
          items-center gap-2 px-3 py-2 rounded-lg cursor-pointer
          transition-all duration-200 hover:bg-accent/50
          ${isExpanded ? 'bg-accent/60 shadow-sm' : ''}
        `}
      >
        {/* Course concept */}
        <span className="text-sm font-medium truncate">{item.concept_name}</span>

        {/* Best match */}
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="text-xs text-muted-foreground truncate text-right">
                {item.best_match || '—'}
              </span>
            </TooltipTrigger>
            {item.best_match && (
              <TooltipContent side="top" className="max-w-xs">
                <p className="text-xs">
                  <strong>Book match:</strong> {item.best_match}
                </p>
                {item.book_chapter_title && (
                  <p className="text-xs text-muted-foreground">
                    {item.book_chapter_title}
                  </p>
                )}
              </TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>

        {/* Similarity bar + number */}
        <div className="flex items-center gap-1.5">
          <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
            <div
              className={`h-full rounded-full ${info.color} transition-all duration-700 ease-out`}
              style={{ width: `${simPct}%` }}
            />
          </div>
          <span className="text-[11px] tabular-nums text-muted-foreground w-7 text-right">
            {simPct}
          </span>
        </div>

        {/* Status */}
        <Badge
          variant={info.label === 'Covered' ? 'default' : info.label === 'Partial' ? 'secondary' : 'destructive'}
          className="text-[10px] justify-center"
        >
          {info.label}
        </Badge>

        {/* Expand caret */}
        {isExpanded ? (
          <ChevronDown className="w-4 h-4 text-muted-foreground transition-transform" />
        ) : (
          <ChevronRight className="w-4 h-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        )}
      </button>

      {/* Expanded Evidence */}
      {isExpanded && (
        <div className="px-2 pb-3 pt-1">
          <EvidencePanel item={item} threshold={threshold} />
        </div>
      )}
    </div>
  );
}

// ── Topic Group ────────────────────────────────────────────────

function TopicGroup({
  group,
  threshold,
  expandedConcept,
  onConceptHover,
  onConceptToggle,
  rowRefs,
}: {
  group: GroupedTopic;
  threshold: number;
  expandedConcept: string | null;
  onConceptHover: (name: string | null) => void;
  onConceptToggle: (name: string) => void;
  rowRefs: React.MutableRefObject<Map<string, HTMLDivElement>>;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const covered = group.items.filter((i) => i.sim_max >= threshold).length;
  const partial = group.items.filter(
    (i) => i.sim_max >= threshold * 0.6 && i.sim_max < threshold,
  ).length;

  return (
    <div className="border rounded-xl overflow-hidden transition-all duration-200">
      {/* Topic header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-accent/30 transition-colors"
      >
        <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
        <span className="text-sm font-semibold flex-1 text-left truncate">
          {group.topic}
        </span>
        <div className="flex items-center gap-1.5">
          {covered > 0 && (
            <Badge variant="default" className="text-[10px] h-5 px-1.5">
              {covered}
            </Badge>
          )}
          {partial > 0 && (
            <Badge variant="secondary" className="text-[10px] h-5 px-1.5">
              {partial}
            </Badge>
          )}
          <Badge variant="outline" className="text-[10px] h-5 px-1.5">
            {group.items.length}
          </Badge>
        </div>
        <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all duration-700"
            style={{ width: `${Math.round(group.avgSim * 100)}%` }}
          />
        </div>
        <span className="text-xs tabular-nums text-muted-foreground w-8 text-right">
          {Math.round(group.avgSim * 100)}%
        </span>
        <ChevronDown
          className={`w-4 h-4 text-muted-foreground transition-transform duration-200 ${isOpen ? 'rotate-0' : '-rotate-90'}`}
        />
      </button>

      {/* Concept rows */}
      {isOpen && (
        <div className="border-t divide-y divide-border/50 animate-in fade-in slide-in-from-top-1 duration-200">
          {group.items.map((item) => (
            <ConceptRow
              key={item.concept_name}
              item={item}
              threshold={threshold}
              isExpanded={expandedConcept === item.concept_name}
              onToggle={() => onConceptToggle(item.concept_name)}
              onHover={(h) => onConceptHover(h ? item.concept_name : null)}
              rowRef={(el) => {
                if (el) rowRefs.current.set(item.concept_name, el);
                else rowRefs.current.delete(item.concept_name);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Coverage Tab ──────────────────────────────────────────

export function CoverageTab() {
  const { state } = useChapterAnalysis();
  const { summaries, selectedBookId, coveredThreshold } = state;
  const [localThreshold, setLocalThreshold] = useState(coveredThreshold);
  const [, setHoveredConcept] = useState<string | null>(null);
  const [expandedConcept, setExpandedConcept] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const summary = summaries.find(
    (s) => s.selected_book_id === selectedBookId,
  );

  const groups = useMemo(
    () => (summary ? groupByTopic(summary.course_coverage) : []),
    [summary],
  );

  const stats = useMemo(() => {
    if (!summary) return { covered: 0, partial: 0, gap: 0, total: 0 };
    let covered = 0,
      partial = 0,
      gap = 0;
    for (const c of summary.course_coverage) {
      if (c.sim_max >= localThreshold) covered++;
      else if (c.sim_max >= localThreshold * 0.6) partial++;
      else gap++;
    }
    return { covered, partial, gap, total: summary.course_coverage.length };
  }, [summary, localThreshold]);

  const handleConceptToggle = useCallback(
    (name: string) => {
      setExpandedConcept((prev) => (prev === name ? null : name));
    },
    [],
  );

  if (!summary) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a book from the Overview tab to view coverage details.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {/* ── Header: Ring + Stats + Threshold ── */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center gap-6 flex-wrap">
            <StatRing {...stats} />

            <div className="flex-1 min-w-[200px] space-y-3">
              {/* Legend row */}
              <div className="flex gap-4">
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                  <span className="text-xs text-muted-foreground">
                    Covered{' '}
                    <span className="font-semibold text-foreground">
                      {stats.covered}
                    </span>
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  <span className="text-xs text-muted-foreground">
                    Partial{' '}
                    <span className="font-semibold text-foreground">
                      {stats.partial}
                    </span>
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                  <span className="text-xs text-muted-foreground">
                    Gap{' '}
                    <span className="font-semibold text-foreground">
                      {stats.gap}
                    </span>
                  </span>
                </div>
              </div>

              {/* Threshold slider */}
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  Threshold
                </span>
                <Slider
                  min={0}
                  max={100}
                  step={5}
                  value={[localThreshold * 100]}
                  onValueChange={([v]) => setLocalThreshold(v / 100)}
                  className="flex-1"
                />
                <span className="text-xs font-semibold tabular-nums w-8 text-right">
                  {(localThreshold * 100).toFixed(0)}%
                </span>
              </div>

              {/* Overall coverage bar */}
              <div className="space-y-1">
                <div className="flex justify-between text-[10px] text-muted-foreground">
                  <span>Overall coverage</span>
                  <span className="font-semibold tabular-nums">
                    {stats.total
                      ? Math.round((stats.covered / stats.total) * 100)
                      : 0}
                    %
                  </span>
                </div>
                <div className="h-2 rounded-full bg-muted overflow-hidden flex">
                  <div
                    className="h-full bg-emerald-500 transition-all duration-700"
                    style={{
                      width: `${stats.total ? (stats.covered / stats.total) * 100 : 0}%`,
                    }}
                  />
                  <div
                    className="h-full bg-amber-500 transition-all duration-700"
                    style={{
                      width: `${stats.total ? (stats.partial / stats.total) * 100 : 0}%`,
                    }}
                  />
                  <div
                    className="h-full bg-red-500 transition-all duration-700"
                    style={{
                      width: `${stats.total ? (stats.gap / stats.total) * 100 : 0}%`,
                    }}
                  />
                </div>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* ── Topic Groups with Bridge Overlay ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <span>Concept Coverage Bridge</span>
            <Badge variant="outline" className="text-[10px]">
              {groups.length} topics
            </Badge>
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Click any concept to reveal text evidence from both the book and your
            course materials side by side.
          </p>
        </CardHeader>
        <CardContent>
          <div ref={containerRef} className="relative">
            <ScrollArea className="max-h-[600px]">
              <div className="space-y-2 pr-2">
                {groups.map((group) => (
                  <TopicGroup
                    key={group.topic}
                    group={group}
                    threshold={localThreshold}
                    expandedConcept={expandedConcept}
                    onConceptHover={setHoveredConcept}
                    onConceptToggle={handleConceptToggle}
                    rowRefs={rowRefs}
                  />
                ))}
              </div>
            </ScrollArea>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
