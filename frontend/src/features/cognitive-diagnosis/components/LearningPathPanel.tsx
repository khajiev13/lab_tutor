import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Loader2, ChevronRight, ArrowUp } from 'lucide-react';
import type { LearningPathDiagnosisResponse } from '../api';

interface LearningPathPanelProps {
  path: LearningPathDiagnosisResponse | null;
  loading?: boolean;
  onSelectSkill?: (skillName: string) => void;
}

export function LearningPathPanel({ path, loading, onSelectSkill }: LearningPathPanelProps) {
  const [expanded, setExpanded] = useState<number | null>(null);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!path || path.steps.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-muted-foreground text-sm">
          No learning path available yet. Compute your mastery first.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Learning Path</CardTitle>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ArUp className="h-3 w-3" />
            <span>+{(path.total_predicted_gain * 100).toFixed(1)}% total gain</span>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          ZPD: {(path.zpd_range[0] * 100).toFixed(0)}% – {(path.zpd_range[1] * 100).toFixed(0)}%
        </p>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {path.steps.map((step) => (
          <div
            key={step.rank}
            className="border rounded-lg overflow-hidden"
          >
            <button
              className="w-full flex items-center gap-3 p-3 hover:bg-muted/50 transition-colors text-left"
              onClick={() => setExpanded(expanded === step.rank ? null : step.rank)}
            >
              <span className="flex-shrink-0 w-6 h-6 rounded-full bg-primary/10 text-primary text-xs font-bold flex items-center justify-center">
                {step.rank}
              </span>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-sm truncate">{step.skill_name}</div>
                <div className="text-xs text-muted-foreground">
                  {(step.current_mastery * 100).toFixed(0)}% → {(step.projected_mastery * 100).toFixed(0)}%
                  <span className="ml-1 text-green-600 dark:text-green-400">
                    (+{(step.predicted_mastery_gain * 100).toFixed(1)}%)
                  </span>
                </div>
              </div>
              <ChevronRight
                className={`h-4 w-4 text-muted-foreground transition-transform ${
                  expanded === step.rank ? 'rotate-90' : ''
                }`}
              />
            </button>

              {expanded === step.rank && (
              <div className="px-3 pb-3 border-t bg-muted/20 space-y-2">
                <p className="text-xs text-muted-foreground pt-2">{step.rationale}</p>
                <div className="flex gap-2 flex-wrap text-xs">
                  <span>Score: <strong>{(step.score * 100).toFixed(0)}</strong></span>
                </div>
                {onSelectSkill && (
                  <button
                    className="text-xs text-primary hover:underline"
                    onClick={() => onSelectSkill(step.skill_name)}
                  >
                    Practice this skill →
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

// Re-export icon alias
function ArUp(props: React.SVGProps<SVGSVGElement>) {
  return <ArrowUp {...props} />;
}
