import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

type Props = {
  concepts: string[];
  highlighted: Set<string>;
};

export function ConceptBank({ concepts, highlighted }: Props) {
  return (
    <Card className="h-full">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-base">Concept bank</CardTitle>
        <Badge variant="secondary">{concepts.length}</Badge>
      </CardHeader>
      <CardContent className="pt-0">
        <Separator className="mb-3" />
        <ScrollArea className="h-[360px] pr-3">
          <div className="space-y-2">
            {concepts.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                No concepts found for this course yet.
              </div>
            ) : (
              concepts.map((name) => (
                <div key={name} className="flex items-center justify-between gap-3">
                  <div className="min-w-0 truncate text-sm">{name}</div>
                  {highlighted.has(name) ? (
                    <Badge variant="default">In merge</Badge>
                  ) : (
                    <Badge variant="outline">—</Badge>
                  )}
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}


