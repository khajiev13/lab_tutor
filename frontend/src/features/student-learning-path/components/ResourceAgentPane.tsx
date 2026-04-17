import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ActiveLearningPathResource } from '../resource-utils';

export function ResourceAgentPane({
  resource,
}: {
  resource: ActiveLearningPathResource;
}) {
  return (
    <Card
      data-testid="resource-agent-pane"
      className="hidden h-full min-h-0 border-border/60 shadow-none md:flex md:flex-col"
    >
      <CardHeader>
        <CardTitle className="text-base">Resource Agent</CardTitle>
      </CardHeader>
      <CardContent className="min-h-0 flex-1 overflow-auto text-sm text-muted-foreground">
        To be implemented. This will guide you through &quot;{resource.title}&quot;.
      </CardContent>
    </Card>
  );
}
