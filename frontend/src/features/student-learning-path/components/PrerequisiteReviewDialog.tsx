import { AlertTriangle, CheckCircle2, GitBranchPlus } from 'lucide-react';

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

function confidenceLabel(confidence: PrerequisiteReviewItem['confidence']) {
  return `${confidence[0]!.toUpperCase()}${confidence.slice(1)} confidence`;
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <GitBranchPlus className="h-5 w-5 text-amber-600" />
            Review prerequisites
          </DialogTitle>
          <DialogDescription>
            Some selected skills depend on earlier foundations. Add those prerequisites to your
            learning path or explicitly confirm that you already know them before continuing.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[60vh] space-y-3 overflow-y-auto pr-1">
          {hasUnresolvedItems ? (
            items.map((item) => (
              <div key={item.name} className="rounded-xl border border-border/70 bg-muted/20 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold">{item.name}</h3>
                      <Badge variant="outline">{confidenceLabel(item.confidence)}</Badge>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Needed for {item.dependentSkillNames.join(', ')}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {item.reasoning || 'This skill appears earlier in the prerequisite graph.'}
                    </p>
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
                  Continue to the build step. If your selected count is outside the course range,
                  you&apos;ll be prompted to adjust it before the build starts.
                </p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="sm:justify-between">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="h-4 w-4" />
            Resolve every prerequisite listed here to continue.
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
      </DialogContent>
    </Dialog>
  );
}
