import { useMemo, useState, useEffect, useCallback } from "react";
import { Card, CardContent } from "@/components/ui/card";
import type { StudentPortfolio, SkillInfo, InsightResponse } from "@/features/arcd-agent/lib/types";
import { generateInsight } from "@/features/arcd-agent/lib/insight-engine";

const LEARNFELL_API =
  import.meta.env.VITE_LEARNFELL_API ?? "http://localhost:8100";

interface InsightPanelProps {
  student: StudentPortfolio;
  skills: SkillInfo[];
  datasetId: string;
}

function SparklesIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z" />
      <path d="M20 3v4" />
      <path d="M22 5h-4" />
      <path d="M4 17v2" />
      <path d="M5 18H3" />
    </svg>
  );
}

function BrainIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4" />
      <path d="M17.599 6.5a3 3 0 0 0 .399-1.375" />
      <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5" />
      <path d="M3.477 10.896a4 4 0 0 1 .585-.396" />
      <path d="M19.938 10.5a4 4 0 0 1 .585.396" />
      <path d="M6 18a4 4 0 0 1-1.967-.516" />
      <path d="M19.967 17.484A4 4 0 0 1 18 18" />
    </svg>
  );
}

function CompassIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
    </svg>
  );
}

function InsightCard({
  icon,
  label,
  text,
  accentClass,
}: {
  icon: React.ReactNode;
  label: string;
  text: string;
  accentClass: string;
}) {
  return (
    <div className="flex gap-4 items-start">
      <div
        className={`shrink-0 flex items-center justify-center w-10 h-10 rounded-lg ${accentClass}`}
      >
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">
          {label}
        </p>
        <p className="text-sm leading-relaxed">{text}</p>
      </div>
    </div>
  );
}

export function InsightPanel({
  student,
  skills,
  datasetId,
}: InsightPanelProps) {
  const localInsight = useMemo(
    () => generateInsight(student, skills),
    [student, skills]
  );

  const [insight, setInsight] = useState<InsightResponse>(localInsight);
  const [isLlm, setIsLlm] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setInsight(localInsight);
    setIsLlm(false);
  }, [localInsight]);

  const fetchLlmInsight = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`${LEARNFELL_API}/api/insight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dataset_id: datasetId,
          student_uid: student.uid,
        }),
      });
      if (resp.ok) {
        const data: InsightResponse = await resp.json();
        setInsight(data);
        setIsLlm(true);
      }
    } catch {
      // keep local insight on failure
    } finally {
      setLoading(false);
    }
  }, [datasetId, student.uid]);

  return (
    <Card className="relative overflow-hidden border-primary/20 bg-gradient-to-br from-primary/[0.03] via-background to-chart-2/[0.03]">
      <div className="absolute top-0 right-0 w-64 h-64 bg-primary/[0.03] rounded-full -translate-y-32 translate-x-32 blur-3xl pointer-events-none" />
      <CardContent className="p-6">
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2">
            <SparklesIcon className="w-5 h-5 text-primary" />
            <h3 className="text-base font-semibold tracking-tight">
              ARCD Insight Engine
            </h3>
            {isLlm && (
              <span className="text-[10px] font-medium bg-primary/10 text-primary px-1.5 py-0.5 rounded-full">
                AI-Enhanced
              </span>
            )}
          </div>
          <button
            onClick={fetchLlmInsight}
            disabled={loading}
            className="text-xs text-muted-foreground hover:text-primary transition-colors disabled:opacity-50 flex items-center gap-1"
          >
            {loading ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <SparklesIcon className="w-3.5 h-3.5" />
                Enhance with AI
              </>
            )}
          </button>
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          <InsightCard
            icon={<SparklesIcon className="w-5 h-5 text-amber-600 dark:text-amber-400" />}
            label="Greeting"
            text={insight.greeting_summary}
            accentClass="bg-amber-100 dark:bg-amber-900/40"
          />
          <InsightCard
            icon={<BrainIcon className="w-5 h-5 text-violet-600 dark:text-violet-400" />}
            label="Knowledge Tracing"
            text={insight.knowledge_tracing_insight}
            accentClass="bg-violet-100 dark:bg-violet-900/40"
          />
          <InsightCard
            icon={<CompassIcon className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />}
            label="Recommended Next Step"
            text={insight.recommended_next_step}
            accentClass="bg-emerald-100 dark:bg-emerald-900/40"
          />
        </div>
      </CardContent>
    </Card>
  );
}
