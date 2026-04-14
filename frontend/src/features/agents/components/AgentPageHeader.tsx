import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Separator } from "@/components/ui/separator";
import type { AgentConfig } from "../config";
import type { AgentStatus } from "./AgentCard";

const STATUS_DISPLAY: Record<
  AgentStatus,
  { label: string; variant: "secondary" | "default" | "outline"; tooltip: string }
> = {
  "not-started": {
    label: "Not Started",
    variant: "secondary",
    tooltip: "This agent hasn't been activated yet.",
  },
  "in-progress": {
    label: "In Progress",
    variant: "default",
    tooltip: "The agent is currently working on your course.",
  },
  completed: {
    label: "Complete",
    variant: "outline",
    tooltip: "The agent has finished processing your course.",
  },
};

interface AgentPageHeaderProps {
  agent: AgentConfig;
  status: AgentStatus;
}

export function AgentPageHeader({ agent, status }: AgentPageHeaderProps) {
  const Icon = agent.icon;
  const cfg = STATUS_DISPLAY[status];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <Avatar className={cn("size-12 rounded-lg", agent.color)}>
          <AvatarFallback className={cn("rounded-lg", agent.color)}>
            <Icon className="size-6" />
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-semibold tracking-tight">
              {agent.name}
            </h1>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Badge variant={cfg.variant}>{cfg.label}</Badge>
                </TooltipTrigger>
                <TooltipContent>{cfg.tooltip}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
          <p className="text-sm text-muted-foreground mt-0.5">
            {agent.description}
          </p>
        </div>
      </div>
      <Separator />
    </div>
  );
}
