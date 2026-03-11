import { cn } from "@/lib/utils";

interface ConnectionStatusProps {
  isStreaming: boolean;
  hasError: boolean;
}

export function ConnectionStatus({ isStreaming, hasError }: ConnectionStatusProps) {
  return (
    <div className="flex items-center gap-1.5">
      <div
        className={cn(
          "w-2 h-2 rounded-full",
          hasError && "bg-red-400",
          isStreaming && !hasError && "bg-amber-400 animate-pulse",
          !isStreaming && !hasError && "bg-muted-foreground"
        )}
      />
      <span className="text-xs text-muted-foreground">
        {hasError ? "Error" : isStreaming ? "Streaming" : "Ready"}
      </span>
    </div>
  );
}
