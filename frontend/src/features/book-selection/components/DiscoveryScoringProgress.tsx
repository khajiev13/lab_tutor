import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Loader2, Search, BarChart3, CheckCircle2, Download, AlertCircle } from 'lucide-react';
import type { BookSelectionSession, SessionStatus } from '../types';

interface DiscoveryScoringProgressProps {
  phase: SessionStatus;
  session: BookSelectionSession | null;
}

const PHASE_CONFIG: Record<
  string,
  { icon: React.ReactNode; label: string; color: string; description: string }
> = {
  discovering: {
    icon: <Search className="h-4 w-4" />,
    label: 'Discovering Books',
    color: 'text-blue-500',
    description: 'Searching for candidate textbooks...',
  },
  scoring: {
    icon: <BarChart3 className="h-4 w-4" />,
    label: 'Scoring Books',
    color: 'text-amber-500',
    description: 'Evaluating and scoring each book...',
  },
  awaiting_review: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    label: 'Ready for Review',
    color: 'text-green-500',
    description: 'Books are scored and ready for your review.',
  },
  downloading: {
    icon: <Download className="h-4 w-4" />,
    label: 'Downloading',
    color: 'text-purple-500',
    description: 'Downloading selected books...',
  },
  completed: {
    icon: <CheckCircle2 className="h-4 w-4" />,
    label: 'Completed',
    color: 'text-green-600',
    description: 'All done!',
  },
  failed: {
    icon: <AlertCircle className="h-4 w-4" />,
    label: 'Failed',
    color: 'text-red-500',
    description: 'An error occurred.',
  },
};

export function DiscoveryScoringProgress({
  phase,
  session,
}: DiscoveryScoringProgressProps) {
  const config = PHASE_CONFIG[phase] ?? PHASE_CONFIG.discovering;
  const isActive = phase === 'discovering' || phase === 'scoring' || phase === 'downloading';

  const scored = session?.progress_scored ?? 0;
  const total = session?.progress_total ?? 0;
  const progressValue = total > 0 ? Math.round((scored / total) * 100) : undefined;

  const progressLabel =
    phase === 'scoring'
      ? `Scored ${scored} of ${total} books`
      : phase === 'downloading'
        ? `Downloaded ${scored} of ${total} books`
        : config.description;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg flex items-center gap-2">
          {isActive && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
          <span className={config.color}>{config.icon}</span>
          {config.label}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {progressValue !== undefined && total > 0 && (
          <div className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                {progressLabel}
              </span>
              <span className="tabular-nums text-muted-foreground">
                {scored}/{total}
              </span>
            </div>
            <Progress value={progressValue} />
          </div>
        )}

        {(progressValue === undefined || total === 0) && (
          <p className="text-sm text-muted-foreground flex items-center gap-2">
            {isActive && <Loader2 className="h-3 w-3 animate-spin" />}
            {config.description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
