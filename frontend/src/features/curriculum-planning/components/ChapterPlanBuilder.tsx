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
import { GripVertical, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
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

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className={cn(
        'flex items-center gap-1.5 px-2 py-1 rounded-md border bg-background text-xs cursor-grab select-none',
        isDragging && 'opacity-50 shadow-lg',
      )}
      title={[doc.topic, doc.summary?.slice(0, 120)].filter(Boolean).join(' — ')}
    >
      <GripVertical className="h-3 w-3 text-muted-foreground shrink-0" />
      <span className="truncate max-w-[160px]">{doc.source_filename}</span>
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
      <div className="flex flex-wrap gap-1.5 min-h-[32px]">
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
      <div className="flex flex-wrap gap-1.5 min-h-[32px]">
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

  return (
    <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
      <div className="space-y-6">
        <div className="flex justify-end">
          <Button onClick={() => void handleSave()} disabled={saving}>
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
