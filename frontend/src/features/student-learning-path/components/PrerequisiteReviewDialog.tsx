import { useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  GitBranchPlus,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export type PrerequisiteReviewItem = {
  name: string;
  dependentSkillNames: string[];
  reasoning: string;
  confidence: 'high' | 'medium' | 'low';
};

type PrerequisiteReviewDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: PrerequisiteReviewItem[];
  onAddToLearningPath: (skillName: string) => void;
  onAcknowledgeKnown: (skillName: string) => void;
  onContinueBuild: () => void;
};

const REASONING_SUMMARY_LIMIT = 140;

function confidenceLabel(confidence: PrerequisiteReviewItem['confidence']) {
  return `${confidence[0]!.toUpperCase()}${confidence.slice(1)} confidence`;
}

function dependentCountLabel(dependentSkillNames: string[]) {
  return dependentSkillNames.length === 1 ? '1 dependent' : `${dependentSkillNames.length} dependents`;
}

function summarizeReasoning(reasoning: string) {
  const normalizedReasoning = reasoning.trim().replace(/\s+/g, ' ');
  if (!normalizedReasoning) {
    return 'This skill appears earlier in the prerequisite graph.';
  }

  const firstSentence = normalizedReasoning.split(/(?<=[.!?])\s+/)[0] ?? normalizedReasoning;
  if (firstSentence.length <= REASONING_SUMMARY_LIMIT) {
    return firstSentence;
  }

  return `${firstSentence.slice(0, REASONING_SUMMARY_LIMIT - 1).trimEnd()}…`;
}

export function PrerequisiteReviewDialog({
  open,
  onOpenChange,
  items,
  onAddToLearningPath,
  onAcknowledgeKnown,
  onContinueBuild,
}: PrerequisiteReviewDialogProps) {
  const hasUnresolvedItems = items.length > 0;
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  const toggleExpanded = (skillName: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(skillName)) {
        next.delete(skillName);
      } else {
        next.add(skillName);
      }
      return next;
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl overflow-hidden p-0">
        <div className="flex max-h-[85vh] flex-col">
          <DialogHeader className="border-b px-6 py-5">
            <DialogTitle className="flex items-center gap-2">
              <GitBranchPlus className="h-5 w-5 text-amber-600" />
              Review prerequisites
            </DialogTitle>
            <DialogDescription>
              Each card shows the prerequisite skill first, then the selected skill it unlocks.
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 space-y-3 overflow-y-auto px-6 py-4">
            {hasUnresolvedItems ? (
              items.map((item) => (
                <div key={item.name} className="rounded-xl border border-border/70 bg-muted/20 p-3">
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">{confidenceLabel(item.confidence)}</Badge>
                      <Badge variant="secondary">{dependentCountLabel(item.dependentSkillNames)}</Badge>
                    </div>

                    <div className="grid gap-3 rounded-lg border border-border/60 bg-background/80 p-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] md:items-start">
                      <div className="min-w-0">
                        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                          Add this prerequisite
                        </p>
                        <p className="mt-1 text-sm font-semibold leading-5">{item.name}</p>
                      </div>

                      <div className="flex items-center justify-center text-muted-foreground">
                        <ArrowRight className="h-4 w-4" />
                      </div>

                      <div className="min-w-0">
                        <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                          Unlocks these selected skills
                        </p>
                        <div className="mt-2 flex flex-wrap gap-1.5">
                          {item.dependentSkillNames.map((dependentSkillName) => (
                            <Badge key={dependentSkillName} variant="secondary" className="max-w-full">
                              {dependentSkillName}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                        Why it shows up
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {summarizeReasoning(item.reasoning)}
                      </p>
                      {item.reasoning.trim() && (
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="-ml-3 h-auto px-3 py-1 text-xs text-muted-foreground"
                          onClick={() => toggleExpanded(item.name)}
                        >
                          {expandedItems.has(item.name) ? (
                            <>
                              <ChevronUp className="h-3.5 w-3.5" />
                              Hide details
                            </>
                          ) : (
                            <>
                              <ChevronDown className="h-3.5 w-3.5" />
                              Show details
                            </>
                          )}
                        </Button>
                      )}
                      {expandedItems.has(item.name) && (
                        <div className="rounded-lg border border-border/70 bg-background/80 p-3 text-xs text-muted-foreground">
                          <p>{item.reasoning.trim()}</p>
                        </div>
                      )}
                    </div>

                    <div className="flex shrink-0 flex-wrap gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="gap-1.5"
                        onClick={() => onAcknowledgeKnown(item.name)}
                      >
                        <CheckCircle2 className="h-4 w-4" />
                        I already know this
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => onAddToLearningPath(item.name)}
                      >
                        <GitBranchPlus className="h-4 w-4" />
                        Add to learning path
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-900 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-100">
                <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0" />
                <div>
                  <p className="font-medium">All prerequisite gaps are resolved.</p>
                  <p className="mt-1 text-sm opacity-90">
                    Continue to the build step. If the selected count falls outside the course range,
                    you&apos;ll be prompted to adjust it before the build starts.
                  </p>
                </div>
              </div>
            )}
          </div>

          <DialogFooter className="border-t bg-background px-6 py-4 sm:justify-between">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <AlertTriangle className="h-4 w-4" />
              Resolve each prerequisite to enable Continue build.
            </div>
            <div className="flex items-center gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              <Button type="button" onClick={onContinueBuild} disabled={hasUnresolvedItems}>
                Continue build
              </Button>
            </div>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
