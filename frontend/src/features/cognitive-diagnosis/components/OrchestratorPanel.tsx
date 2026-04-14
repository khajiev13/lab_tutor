import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Activity,
  ArrowRight,
  BarChart2,
  Brain,
  Dumbbell,
  Map,
  RefreshCw,
  Repeat2,
} from 'lucide-react';
import type { PortfolioResponse } from '../api';

interface OrchestratorPanelProps {
  portfolio: PortfolioResponse;
}

interface PipelineStage {
  id: string;
  label: string;
  agent: string;
  icon: React.ReactNode;
  color: string;
  bg: string;
  border: string;
  stats: { label: string; value: string }[];
}

export function OrchestratorPanel({ portfolio }: OrchestratorPanelProps) {
  const { mastery, learning_path, pco_skills, stats } = portfolio;

  const avgMastery = stats.average_mastery ?? 0;
  const masteredCount = stats.mastered_skills ?? 0;
  const totalSkills = stats.total_skills ?? mastery.length;

  const stages: PipelineStage[] = [
    {
      id: 'assess',
      label: 'Assess',
      agent: 'Neural Model',
      icon: <Brain className="h-4 w-4" />,
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      border: 'border-blue-200 dark:border-blue-800',
      stats: [
        { label: 'Skills tracked', value: String(totalSkills) },
        { label: 'Avg mastery', value: `${(avgMastery * 100).toFixed(0)}%` },
        { label: 'Mastered', value: String(masteredCount) },
      ],
    },
    {
      id: 'pathgen',
      label: 'PathGen',
      agent: 'Path Generator',
      icon: <Map className="h-4 w-4" />,
      color: 'text-purple-600 dark:text-purple-400',
      bg: 'bg-purple-50 dark:bg-purple-900/20',
      border: 'border-purple-200 dark:border-purple-800',
      stats: [
        { label: 'Path steps', value: learning_path ? String(learning_path.path_length) : '—' },
        {
          label: 'Predicted gain',
          value: learning_path
            ? `+${(learning_path.total_predicted_gain * 100).toFixed(1)}%`
            : '—',
        },
        {
          label: 'ZPD range',
          value: learning_path
            ? `${(learning_path.zpd_range[0] * 100).toFixed(0)}–${(learning_path.zpd_range[1] * 100).toFixed(0)}%`
            : '—',
        },
      ],
    },
    {
      id: 'revfell',
      label: 'RevFell',
      agent: 'Review Fellow',
      icon: <Repeat2 className="h-4 w-4" />,
      color: 'text-orange-600 dark:text-orange-400',
      bg: 'bg-orange-50 dark:bg-orange-900/20',
      border: 'border-orange-200 dark:border-orange-800',
      stats: [
        { label: 'PCO skills', value: String(pco_skills.length) },
        { label: 'PCO rate', value: totalSkills ? `${((pco_skills.length / totalSkills) * 100).toFixed(0)}%` : '—' },
        { label: 'Status', value: pco_skills.length === 0 ? 'Healthy' : 'Needs Review' },
      ],
    },
    {
      id: 'adaex',
      label: 'AdaEx',
      agent: 'Adaptive Exercise',
      icon: <Dumbbell className="h-4 w-4" />,
      color: 'text-green-600 dark:text-green-400',
      bg: 'bg-green-50 dark:bg-green-900/20',
      border: 'border-green-200 dark:border-green-800',
      stats: [
        {
          label: 'Eligible skills',
          value: String(mastery.filter((s) => s.status !== 'not_started').length),
        },
        { label: 'Below ZPD', value: String(mastery.filter((s) => s.status === 'below').length) },
        { label: 'In ZPD', value: String(mastery.filter((s) => s.status === 'at').length) },
      ],
    },
    {
      id: 'reassess',
      label: 'Reassess',
      agent: 'Loop Controller',
      icon: <RefreshCw className="h-4 w-4" />,
      color: 'text-slate-600 dark:text-slate-400',
      bg: 'bg-slate-50 dark:bg-slate-900/20',
      border: 'border-slate-200 dark:border-slate-700',
      stats: [
        {
          label: 'Deviation check',
          value: pco_skills.length > 0 ? 'Replan needed' : 'Stable',
        },
        {
          label: 'Loop status',
          value: pco_skills.length > 0 ? 'Active' : 'Finalized',
        },
        { label: 'Max iterations', value: '2' },
      ],
    },
  ];

  return (
    <div className="space-y-6">
      {/* Pipeline flow */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-2">
            <Activity className="h-4 w-4 text-primary" />
            ARCD Orchestration Pipeline
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            LangGraph closed-loop cycle — runs up to 2 reassess iterations
          </p>
        </CardHeader>
        <CardContent>
          {/* Flow diagram */}
          <div className="flex flex-wrap items-center gap-1 mb-6">
            {stages.map((stage, i) => (
              <div key={stage.id} className="flex items-center gap-1">
                <div
                  className={`flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs font-medium ${stage.bg} ${stage.border} ${stage.color}`}
                >
                  {stage.icon}
                  {stage.label}
                </div>
                {i < stages.length - 1 && (
                  <ArrowRight className="h-3 w-3 text-muted-foreground shrink-0" />
                )}
              </div>
            ))}
            {/* Loop arrow back to pathgen */}
            <div className="flex items-center gap-1 text-xs text-muted-foreground ml-1">
              <RefreshCw className="h-3 w-3" />
              <span>if deviation</span>
            </div>
          </div>

          {/* Per-stage stat cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {stages.map((stage) => (
              <div
                key={stage.id}
                className={`rounded-lg border p-3 space-y-2 ${stage.border} ${stage.bg}`}
              >
                <div className={`flex items-center gap-2 font-medium text-sm ${stage.color}`}>
                  {stage.icon}
                  <span>{stage.agent}</span>
                </div>
                <div className="space-y-1">
                  {stage.stats.map((stat) => (
                    <div key={stat.label} className="flex justify-between text-xs gap-2">
                      <span className="text-muted-foreground">{stat.label}</span>
                      <span className="font-semibold tabular-nums">{stat.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Overall portfolio health */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <BarChart2 className="h-4 w-4 text-primary" />
            Portfolio Health Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <HealthStat
              label="Total Skills"
              value={totalSkills}
              badge={null}
            />
            <HealthStat
              label="Mastered"
              value={masteredCount}
              badge={{ text: `${totalSkills ? ((masteredCount / totalSkills) * 100).toFixed(0) : 0}%`, color: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400' }}
            />
            <HealthStat
              label="Avg Mastery"
              value={`${(avgMastery * 100).toFixed(1)}%`}
              badge={null}
            />
            <HealthStat
              label="PCO Risks"
              value={pco_skills.length}
              badge={
                pco_skills.length > 0
                  ? { text: 'Review', color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-400' }
                  : { text: 'Healthy', color: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400' }
              }
            />
          </div>

          {/* Status distribution */}
          <div className="mt-4">
            <p className="text-xs text-muted-foreground mb-2">Skill status distribution</p>
            <StatusDistributionBar mastery={portfolio.mastery} />
          </div>
        </CardContent>
      </Card>

      {/* Generated at */}
      <p className="text-xs text-muted-foreground">
        Portfolio generated: {portfolio.generated_at ? new Date(portfolio.generated_at).toLocaleString() : 'unknown'}
      </p>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function HealthStat({
  label,
  value,
  badge,
}: {
  label: string;
  value: string | number;
  badge: { text: string; color: string } | null;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-bold tabular-nums">{value}</p>
      {badge && (
        <span className={`inline-block text-xs px-1.5 py-0.5 rounded-full font-medium ${badge.color}`}>
          {badge.text}
        </span>
      )}
    </div>
  );
}

function StatusDistributionBar({ mastery }: { mastery: PortfolioResponse['mastery'] }) {
  const total = mastery.length || 1;
  const counts = {
    above: mastery.filter((s) => s.status === 'above').length,
    at: mastery.filter((s) => s.status === 'at').length,
    below: mastery.filter((s) => s.status === 'below').length,
    not_started: mastery.filter((s) => s.status === 'not_started').length,
  };

  const segments = [
    { label: 'Mastered', count: counts.above, color: 'bg-green-500' },
    { label: 'In Progress', count: counts.at, color: 'bg-blue-500' },
    { label: 'Learning', count: counts.below, color: 'bg-orange-500' },
    { label: 'Not Started', count: counts.not_started, color: 'bg-muted' },
  ];

  return (
    <div className="space-y-2">
      <div className="flex h-3 rounded-full overflow-hidden gap-0.5">
        {segments.map((seg) =>
          seg.count > 0 ? (
            <div
              key={seg.label}
              className={`${seg.color} transition-all`}
              style={{ width: `${(seg.count / total) * 100}%` }}
              title={`${seg.label}: ${seg.count}`}
            />
          ) : null,
        )}
      </div>
      <div className="flex flex-wrap gap-3">
        {segments.map((seg) => (
          <div key={seg.label} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <div className={`h-2 w-2 rounded-full ${seg.color}`} />
            <span>{seg.label}</span>
            <span className="font-medium text-foreground">({seg.count})</span>
          </div>
        ))}
      </div>
    </div>
  );
}
