import { useState } from 'react';
import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  useDroppable,
  useDraggable,
} from '@dnd-kit/core';
import type { DragEndEvent } from '@dnd-kit/core';
import { GripVertical, Loader2, Info } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { saveChapterPlan } from '../api';
import type { ChapterPlan, ChapterPlanResponse, DocumentInfo } from '../types';

/* ── DocumentCard ─────────────────────────────────────────────── */

function DocumentCard({
  doc,
  containerId,
}: {
  doc: DocumentInfo;
  containerId: string;
}) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: doc.id,
    data: { containerId },
  });

  const displayTitle = doc.topic || doc.source_filename;
  const hasSummary = Boolean(doc.summary);

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={cn(
        'flex items-center gap-2 px-2.5 py-1.5 rounded-md border bg-background cursor-grab select-none transition-shadow w-full group',
        isDragging && 'opacity-50 shadow-lg ring-2 ring-primary/30',
        !isDragging && 'hover:shadow-sm',
      )}
    >
      <GripVertical className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-tight line-clamp-1">
          {displayTitle}
        </p>
        {doc.topic && (
          <p className="text-[11px] text-muted-foreground/60 leading-tight truncate">
            {doc.source_filename}
          </p>
        )}
      </div>
      {hasSummary && (
        <Popover>
          <PopoverTrigger asChild>
            <button
              type="button"
              aria-label={`Details for ${displayTitle}`}
              className="shrink-0 p-1 rounded-md text-muted-foreground/50 hover:text-foreground hover:bg-muted transition-colors opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => e.stopPropagation()}
            >
              <Info className="h-3.5 w-3.5" />
            </button>
          </PopoverTrigger>
          <PopoverContent side="right" align="start" className="w-80 space-y-2">
            <h4 className="text-sm font-semibold">{displayTitle}</h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {doc.summary}
            </p>
            <p className="text-[11px] text-muted-foreground/60 pt-1 border-t">
              {doc.source_filename}
            </p>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

/* ── ChapterCard ──────────────────────────────────────────────── */

function ChapterCard({
  chapter,
  docs,
  allDocuments,
}: {
  chapter: ChapterPlan;
  docs: string[];
  allDocuments: DocumentInfo[];
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `chapter-${chapter.number}` });
  const chapterDocs = allDocuments.filter((d) => docs.includes(d.id));

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'rounded-lg border p-4 space-y-3 min-h-[160px] transition-colors',
        isOver && 'border-primary/60 bg-primary/5',
      )}
    >
      <div>
        <h3 className="font-medium text-sm">{chapter.title}</h3>
        {chapter.description && (
          <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
            {chapter.description}
          </p>
        )}
      </div>
      <div className="grid gap-1.5 min-h-[32px]">
        {chapterDocs.map((doc) => (
          <DocumentCard key={doc.id} doc={doc} containerId={`chapter-${chapter.number}`} />
        ))}
        {chapterDocs.length === 0 && (
          <p className="text-xs text-muted-foreground italic">Drop documents here</p>
        )}
      </div>
    </div>
  );
}

/* ── UnassignedPool ───────────────────────────────────────────── */

function UnassignedPool({
  docIds,
  allDocuments,
}: {
  docIds: string[];
  allDocuments: DocumentInfo[];
}) {
  const { setNodeRef, isOver } = useDroppable({ id: 'unassigned' });
  const docs = allDocuments.filter((d) => docIds.includes(d.id));

  return (
    <div
      ref={setNodeRef}
      className={cn(
        'rounded-lg border border-dashed p-4 space-y-2 transition-colors',
        isOver && 'border-primary/60 bg-primary/5',
      )}
    >
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Unassigned Documents
      </p>
      <div className="grid gap-1.5 sm:grid-cols-2 min-h-[32px]">
        {docs.map((doc) => (
          <DocumentCard key={doc.id} doc={doc} containerId="unassigned" />
        ))}
      </div>
    </div>
  );
}

/* ── ChapterPlanBuilder ───────────────────────────────────────── */

interface ChapterPlanBuilderProps {
  initialPlan: ChapterPlanResponse;
  onSave: (updated: ChapterPlanResponse) => void;
  courseId: number;
}

export function ChapterPlanBuilder({ initialPlan, onSave, courseId }: ChapterPlanBuilderProps) {
  const [chapters, setChapters] = useState(initialPlan.chapters);
  const [unassignedIds, setUnassignedIds] = useState<string[]>(
    initialPlan.unassigned_documents.map((d) => d.id),
  );
  const [saving, setSaving] = useState(false);
  const allDocuments = initialPlan.all_documents;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
  );

  const findContainer = (docId: string): string => {
    if (unassignedIds.includes(docId)) return 'unassigned';
    const ch = chapters.find((c) => c.assigned_documents.includes(docId));
    return ch ? `chapter-${ch.number}` : 'unassigned';
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    const docId = String(active.id);
    const targetContainer = String(over.id);
    const sourceContainer = findContainer(docId);
    if (sourceContainer === targetContainer) return;

    // Remove from source
    if (sourceContainer === 'unassigned') {
      setUnassignedIds((prev) => prev.filter((id) => id !== docId));
    } else {
      const chNum = Number(sourceContainer.replace('chapter-', ''));
      setChapters((prev) =>
        prev.map((c) =>
          c.number === chNum
            ? { ...c, assigned_documents: c.assigned_documents.filter((id) => id !== docId) }
            : c,
        ),
      );
    }

    // Add to target
    if (targetContainer === 'unassigned') {
      setUnassignedIds((prev) => [...prev, docId]);
    } else {
      const chNum = Number(targetContainer.replace('chapter-', ''));
      setChapters((prev) =>
        prev.map((c) =>
          c.number === chNum
            ? { ...c, assigned_documents: [...c.assigned_documents, docId] }
            : c,
        ),
      );
    }
  };

  // Chapters with at least one document
  const visibleChapters = chapters.filter((c) => c.assigned_documents.length > 0);

  const handleSave = async () => {
    setSaving(true);
    try {
      const result = await saveChapterPlan(courseId, { chapters: visibleChapters });
      onSave(result);
      toast.success('Chapter plan saved');
    } catch {
      toast.error('Failed to save chapter plan');
    } finally {
      setSaving(false);
    }
  };

  const hasUnassigned = unassignedIds.length > 0;

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="space-y-6">
        <div className="flex items-center justify-end gap-3">
          {hasUnassigned && (
            <p className="text-xs text-muted-foreground">
              Assign all documents to chapters before saving
            </p>
          )}
          <Button onClick={() => void handleSave()} disabled={saving || hasUnassigned}>
            {saving && <Loader2 className="h-4 w-4 animate-spin mr-2" />}
            Save Changes
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {visibleChapters.map((ch) => (
            <ChapterCard
              key={ch.number}
              chapter={ch}
              docs={ch.assigned_documents}
              allDocuments={allDocuments}
            />
          ))}
        </div>

        {unassignedIds.length > 0 && (
          <UnassignedPool docIds={unassignedIds} allDocuments={allDocuments} />
        )}
      </div>
    </DndContext>
  );
}
