import { AlertCircle, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";

export function CourseProgressFeedback({ error, onRetry }: { error: boolean; onRetry: () => void }) {
  if (error) {
    return (
      <div role="alert" className="flex flex-col items-start gap-4 rounded-xl border p-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <AlertCircle className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
          <div>
            <p className="font-medium">Could not load course progress</p>
            <p className="mt-1 text-sm text-muted-foreground">Try again to check which step is available.</p>
          </div>
        </div>
        <Button variant="outline" onClick={onRetry}>Try again</Button>
      </div>
    );
  }

  return (
    <div role="status" className="flex items-center justify-center gap-3 rounded-xl border p-12 text-sm text-muted-foreground">
      <Loader2 className="size-5 animate-spin" />
      Checking course progress…
    </div>
  );
}
