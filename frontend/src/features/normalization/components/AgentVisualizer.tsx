import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle2, Loader2, ShieldCheck, Sparkles } from 'lucide-react';

type Props = {
  activePhase: 'generation' | 'validation' | 'complete';
  agentActivity: string;
};

export function AgentVisualizer({ activePhase, agentActivity }: Props) {
  const genActive = activePhase === 'generation';
  const valActive = activePhase === 'validation';
  const isComplete = activePhase === 'complete';

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card className={genActive ? 'border-primary shadow-sm animate-pulse' : undefined}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            Generation Agent
          </CardTitle>
          <Badge variant={genActive ? 'default' : 'secondary'}>
            {genActive ? 'Active' : 'Idle'}
          </Badge>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Proposes merges + relationships based on concept names and prior weak patterns.
        </CardContent>
      </Card>

      <Card className={valActive ? 'border-primary shadow-sm animate-pulse' : undefined}>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Validation Agent
          </CardTitle>
          <Badge variant={valActive ? 'default' : 'secondary'}>
            {valActive ? 'Active' : 'Idle'}
          </Badge>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Validates proposals using definitions/evidence from your course documents.
        </CardContent>
      </Card>

      <div className="md:col-span-2">
        <Card>
          <CardHeader className="py-3">
            <CardTitle className="text-sm">Current activity</CardTitle>
          </CardHeader>
          <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
            {isComplete ? (
              <CheckCircle2 className="h-4 w-4 text-green-600" />
            ) : (
              <Loader2 className="h-4 w-4 animate-spin" />
            )}
            <span>{agentActivity || '—'}</span>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


