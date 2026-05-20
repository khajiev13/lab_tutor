import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { Bot } from "lucide-react";
import { AGENTS, type AgentConfig } from "../config";
import { AgentCard, type AgentStatus } from "./AgentCard";

interface AgentHubGridProps {
  agents?: AgentConfig[];
  courseId: number;
  isLoading: boolean;
  statuses: Record<string, { status: AgentStatus; progress?: number; lastActivity?: string }>;
  cardClickOverrides?: Partial<Record<string, () => void>>;
}

function AgentCardSkeleton() {
  return (
    <div className="rounded-lg border p-6 space-y-4">
      <div className="flex items-start gap-4">
        <Skeleton className="size-10 rounded-lg" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-40" />
          <Skeleton className="h-4 w-60" />
        </div>
        <Skeleton className="h-5 w-20 rounded-full" />
      </div>
      <Skeleton className="h-1.5 w-full" />
    </div>
  );
}

export function AgentHubGrid({
  agents = AGENTS,
  courseId,
  isLoading,
  statuses,
  cardClickOverrides,
}: AgentHubGridProps) {
  if (isLoading) {
    const skeletonCount = Math.min(Math.max(agents.length, 1), 3);
    return (
      <div className="grid gap-4 md:grid-cols-2">
        {Array.from({ length: skeletonCount }, (_, index) => (
          <AgentCardSkeleton key={index} />
        ))}
      </div>
    );
  }

  if (agents.length === 0) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <Bot />
          </EmptyMedia>
          <EmptyTitle>No agents available</EmptyTitle>
          <EmptyDescription>
            Agents will appear here once they are configured for this course.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {agents.map((agent) => {
        const info = statuses[agent.id];
        return (
          <AgentCard
            key={agent.id}
            agent={agent}
            courseId={courseId}
            status={info?.status}
            progress={info?.progress}
            lastActivity={info?.lastActivity}
            onCardClick={cardClickOverrides?.[agent.id]}
          />
        );
      })}
    </div>
  );
}
