import { useNavigate } from "react-router-dom";
import { Clock } from "lucide-react";

import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
} from "@/components/ui/empty";
import { Progress } from "@/components/ui/progress";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { AgentConfig } from "../config";

export type AgentStatus = "not-started" | "in-progress" | "completed";

interface AgentCardProps {
  agent: AgentConfig;
  courseId: number;
  status?: AgentStatus;
  progress?: number;
  lastActivity?: string;
  hideStatus?: boolean;
  onCardClick?: () => void;
}

const STATUS_CONFIG: Record<
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

export function AgentCard({
  agent,
  courseId,
  status,
  progress,
  lastActivity,
  hideStatus = false,
  onCardClick,
}: AgentCardProps) {
  const navigate = useNavigate();
  const Icon = agent.icon;

  if (!agent.enabled) {
    return (
      <Card className="opacity-60">
        <CardContent className="p-0">
          <Empty className="min-h-[180px] border-0">
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Icon />
              </EmptyMedia>
              <EmptyTitle className="text-base">{agent.name}</EmptyTitle>
              <EmptyDescription>{agent.description}</EmptyDescription>
            </EmptyHeader>
            <Badge variant="secondary">Coming Soon</Badge>
          </Empty>
        </CardContent>
      </Card>
    );
  }

  const statusCfg = status ? STATUS_CONFIG[status] : null;
  const showStatus = !hideStatus && statusCfg;
  const handleClick = () => {
    if (onCardClick) {
      onCardClick();
      return;
    }
    navigate(`/courses/${courseId}/${agent.route}`);
  };

  return (
    <HoverCard>
      <HoverCardTrigger asChild>
        <Card
          className="cursor-pointer transition-shadow hover:shadow-md"
          onClick={handleClick}
        >
          <CardHeader className="flex flex-row items-start gap-4 space-y-0">
            <Avatar className={cn("size-10 rounded-lg", agent.color)}>
              <AvatarFallback className={cn("rounded-lg", agent.color)}>
                <Icon className="size-5" />
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 space-y-1">
              <CardTitle className="text-base">{agent.name}</CardTitle>
              <CardDescription className="line-clamp-2">
                {agent.description}
              </CardDescription>
            </div>
            {showStatus && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge variant={statusCfg.variant}>{statusCfg.label}</Badge>
                  </TooltipTrigger>
                  <TooltipContent>{statusCfg.tooltip}</TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </CardHeader>
          {progress !== undefined && (
            <CardContent className="pt-0">
              <Progress value={progress} className="h-1.5" />
            </CardContent>
          )}
        </Card>
      </HoverCardTrigger>
      <HoverCardContent side="top" className="w-64">
        <div className="space-y-2">
          <p className="text-sm font-medium">{agent.name}</p>
          {progress !== undefined && (
            <p className="text-sm text-muted-foreground">
              Progress: {Math.round(progress)}%
            </p>
          )}
          {lastActivity && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Clock className="size-3" />
              {lastActivity}
            </p>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
