import {
  BookOpen,
  TrendingUp,
  Layers,
  Lightbulb,
  AlertTriangle,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import type { CurriculumResponse } from "../types";

interface StatItem {
  label: string;
  value: number;
  icon: React.ReactNode;
  className?: string;
}

export function CurriculumStats({
  curriculum,
}: {
  curriculum: CurriculumResponse;
}) {
  const chapters = curriculum.chapters;

  const totalBookSkills = chapters.reduce(
    (sum, ch) => sum + ch.skills.filter((s) => s.source === "book").length,
    0
  );
  const totalMarketSkills = chapters.reduce(
    (sum, ch) =>
      sum + ch.skills.filter((s) => s.source === "market_demand").length,
    0
  );
  const uniqueConcepts = new Set(
    chapters.flatMap((ch) => [
      ...ch.sections.flatMap((s) => s.concepts.map((c) => c.name)),
      ...ch.skills.flatMap((sk) => sk.concepts.map((c) => c.name)),
    ])
  ).size;
  const gaps = chapters.reduce(
    (sum, ch) =>
      sum +
      ch.skills.filter(
        (s) => s.source === "market_demand" && s.status === "gap"
      ).length,
    0
  );

  const stats: StatItem[] = [
    {
      label: "Chapters",
      value: chapters.length,
      icon: <Layers className="size-4 text-blue-500" />,
    },
    {
      label: "Book Skills",
      value: totalBookSkills,
      icon: <BookOpen className="size-4 text-violet-500" />,
    },
    {
      label: "Market Skills",
      value: totalMarketSkills,
      icon: <TrendingUp className="size-4 text-emerald-500" />,
    },
    {
      label: "Concepts",
      value: uniqueConcepts,
      icon: <Lightbulb className="size-4 text-amber-500" />,
    },
    {
      label: "Gaps",
      value: gaps,
      icon: <AlertTriangle className="size-4 text-red-500" />,
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {stats.map((stat) => (
        <Card key={stat.label} className="shadow-none py-0">
          <CardContent className="px-4 py-3 flex items-center gap-3">
            <div className="rounded-md bg-muted p-2">{stat.icon}</div>
            <div>
              <p className="text-lg font-bold leading-none">{stat.value}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {stat.label}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
