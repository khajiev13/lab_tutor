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
      <DialogContent
        maxWidthClassName="sm:max-w-[min(88rem,calc(100%-3rem))]"
        className="overflow-hidden p-0"
      >
        <div className="flex max-h-[88vh] flex-col">
          <DialogHeader className="border-b px-6 py-6 sm:px-8">
            <div className="flex flex-wrap items-center gap-3">
              <DialogTitle className="flex items-center gap-2">
                <GitBranchPlus className="h-5 w-5 text-amber-600" />
                Review prerequisites
              </DialogTitle>
              {hasUnresolvedItems && (
                <Badge variant="outline" className="rounded-full">
                  {items.length} prerequisite {items.length === 1 ? 'gap' : 'gaps'} to review
                </Badge>
              )}
            </div>
            <DialogDescription className="max-w-3xl text-sm leading-6">
              We paused before building because some of the skills you selected usually depend on
              earlier foundations. Taking a minute here helps your learning path feel smoother
              instead of jumping ahead too quickly.
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 space-y-4 overflow-y-auto px-6 py-5 sm:px-8 sm:py-6">
            {hasUnresolvedItems ? (
              items.map((item) => (
                <div key={item.name} className="rounded-2xl border border-border/70 bg-muted/20 p-4 sm:p-5">
                  <div className="space-y-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="rounded-full">
                        {confidenceLabel(item.confidence)}
                      </Badge>
                      <Badge variant="secondary" className="rounded-full">
                        {dependentCountLabel(item.dependentSkillNames)}
                      </Badge>
                    </div>

                    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(20rem,1fr)]">
                      <div className="space-y-4">
                        <div className="grid gap-3 lg:grid-cols-[minmax(0,0.95fr)_auto_minmax(0,1.05fr)] lg:items-stretch">
                          <div className="min-w-0 rounded-xl border border-border/60 bg-background/80 p-4">
                            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                              Recommended first
                            </p>
                            <p className="mt-2 text-base font-semibold leading-7">{item.name}</p>
                          </div>

                          <div className="hidden items-center justify-center text-muted-foreground lg:flex">
                            <ArrowRight className="h-4 w-4" />
                          </div>

                          <div className="min-w-0 rounded-xl border border-border/60 bg-background/80 p-4">
                            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                              It supports these selected skills
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {item.dependentSkillNames.map((dependentSkillName) => (
                                <Badge
                                  key={dependentSkillName}
                                  variant="secondary"
                                  className="h-auto max-w-full rounded-full px-3 py-1 text-left text-xs leading-5 whitespace-normal"
                                >
                                  {dependentSkillName}
                                </Badge>
                              ))}
                            </div>
                          </div>
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div className="rounded-xl border border-border/60 bg-background/70 p-4">
                          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                            Skill connection
                          </p>
                          <p className="mt-2 text-sm leading-6 text-muted-foreground">
                            {summarizeReasoning(item.reasoning)}
                          </p>
                          {item.reasoning.trim() && (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="-ml-3 mt-2 h-auto px-3 py-1 text-xs text-muted-foreground"
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
                            <div className="mt-2 rounded-lg border border-border/70 bg-background/80 p-3 text-xs leading-5 text-muted-foreground">
                              <p>{item.reasoning.trim()}</p>
                            </div>
                          )}
                        </div>

                        <div className="rounded-xl border border-border/60 bg-background/70 p-4">
                          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">
                            Choose how to continue
                          </p>
                          <div className="mt-3 flex shrink-0 flex-wrap gap-2">
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

          <DialogFooter className="border-t bg-background px-6 py-4 sm:justify-between sm:px-8">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <AlertTriangle className="h-4 w-4" />
              Resolve or acknowledge each item to unlock Continue build.
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
