import {
  BookOpen,
  Briefcase,
  Layers,
  FileText,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";

interface StatItem {
  label: string;
  value: number;
  icon: LucideIcon;
  iconClassName: string;
}

export function CurriculumStats({
  courseChapterCount,
  transcriptFileCount,
  bookSkillCount,
  marketSkillCount,
  jobPostingCount,
}: {
  courseChapterCount: number;
  transcriptFileCount: number;
  bookSkillCount: number;
  marketSkillCount: number;
  jobPostingCount: number;
}) {
  const stats: StatItem[] = [
    {
      label: "Course Chapters",
      value: courseChapterCount,
      icon: Layers,
      iconClassName: "text-blue-500",
    },
    {
      label: "Transcript Files",
      value: transcriptFileCount,
      icon: FileText,
      iconClassName: "text-sky-500",
    },
    {
      label: "Book Skills",
      value: bookSkillCount,
      icon: BookOpen,
      iconClassName: "text-violet-500",
    },
    {
      label: "Market Skills",
      value: marketSkillCount,
      icon: TrendingUp,
      iconClassName: "text-emerald-500",
    },
    {
      label: "Job Postings",
      value: jobPostingCount,
      icon: Briefcase,
      iconClassName: "text-amber-500",
    },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
      {stats.map((stat) => (
        <Card key={stat.label} className="shadow-none py-0">
          <CardContent className="px-4 py-3 flex items-center gap-3">
            <div className="rounded-md bg-muted p-2">
              <stat.icon className={`size-4 ${stat.iconClassName}`} />
            </div>
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
