import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ActiveLearningPathResource } from '../resource-utils';

export function ResourceAgentPane({
  resource,
}: {
  resource: ActiveLearningPathResource;
}) {
  return (
    <Card data-testid="resource-agent-pane" className="hidden border-border/60 shadow-none md:block">
      <CardHeader>
        <CardTitle className="text-base">Resource Agent</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        To be implemented. This will guide you through &quot;{resource.title}&quot;.
      </CardContent>
    </Card>
  );
}
