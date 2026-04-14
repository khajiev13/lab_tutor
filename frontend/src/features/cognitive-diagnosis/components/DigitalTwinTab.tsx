import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Fingerprint,
  TrendingUp,
  Zap,
} from 'lucide-react';
import type { PortfolioResponse, SkillMastery } from '../api';
import { MasteryRadarChart } from './MasteryRadarChart';

interface DigitalTwinTabProps {
  portfolio: PortfolioResponse;
  onPracticeSkill?: (skillName: string) => void;
}

function CognitiveHealthBar({ value, label }: { value: number; label: string }) {
  const pct = Math.round(value * 100);
  const color =
    pct >= 70 ? 'bg-emerald-500' : pct >= 40 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function velocityLabel(m: SkillMastery): { label: string; color: string } {
  if (m.attempt_count === 0) return { label: 'Not started', color: 'text-muted-foreground' };
  const accuracy = m.correct_count / m.attempt_count;
  if (accuracy >= 0.8) return { label: 'Strong', color: 'text-emerald-600 dark:text-emerald-400' };
  if (accuracy >= 0.5) return { label: 'Moderate', color: 'text-amber-600 dark:text-amber-400' };
  return { label: 'Needs work', color: 'text-red-600 dark:text-red-400' };
}

export function DigitalTwinTab({ portfolio, onPracticeSkill }: DigitalTwinTabProps) {
  const { mastery, stats, pco_skills } = portfolio;

  const avgMastery = stats.average_mastery;
  const avgDecay =
    mastery.length > 0
      ? mastery.reduce((s, m) => s + m.decay, 0) / mastery.length
      : 0;
  const avgAccuracy =
    mastery.filter((m) => m.attempt_count > 0).length > 0
      ? mastery
          .filter((m) => m.attempt_count > 0)
          .reduce((s, m) => s + m.correct_count / m.attempt_count, 0) /
        mastery.filter((m) => m.attempt_count > 0).length
      : 0;

  const atRisk = pco_skills.length;
  const aboveMastery = mastery.filter((m) => m.status === 'above').length;
  const notStarted = mastery.filter((m) => m.status === 'not_started').length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Fingerprint className="h-5 w-5 text-primary" />
        <div>
          <h2 className="font-semibold text-lg">Student Digital Twin</h2>
          <p className="text-xs text-muted-foreground">
            Cognitive snapshot — mastery, retention, and learning velocity
          </p>
        </div>
      </div>

      {/* ── Stat Cards ───────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card className="bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Brain className="h-4 w-4 text-emerald-600" />
              <span className="text-xs text-muted-foreground">Avg Mastery</span>
            </div>
            <p className="text-2xl font-bold text-emerald-700 dark:text-emerald-400">
              {(avgMastery * 100).toFixed(0)}%
            </p>
          </CardContent>
        </Card>

        <Card className="bg-blue-50 dark:bg-blue-950/30 border-blue-200 dark:border-blue-800">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Activity className="h-4 w-4 text-blue-600" />
              <span className="text-xs text-muted-foreground">Retention</span>
            </div>
            <p className="text-2xl font-bold text-blue-700 dark:text-blue-400">
              {(avgDecay * 100).toFixed(0)}%
            </p>
          </CardContent>
        </Card>

        <Card className="bg-violet-50 dark:bg-violet-950/30 border-violet-200 dark:border-violet-800">
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <Zap className="h-4 w-4 text-violet-600" />
              <span className="text-xs text-muted-foreground">Accuracy</span>
            </div>
            <p className="text-2xl font-bold text-violet-700 dark:text-violet-400">
              {(avgAccuracy * 100).toFixed(0)}%
            </p>
          </CardContent>
        </Card>

        <Card
          className={
            atRisk > 0
              ? 'bg-red-50 dark:bg-red-950/30 border-red-200 dark:border-red-800'
              : 'bg-slate-50 dark:bg-slate-950/30'
          }
        >
          <CardContent className="pt-4 pb-3">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className={`h-4 w-4 ${atRisk > 0 ? 'text-red-500' : 'text-muted-foreground'}`} />
              <span className="text-xs text-muted-foreground">PCO Risks</span>
            </div>
            <p className={`text-2xl font-bold ${atRisk > 0 ? 'text-red-600 dark:text-red-400' : 'text-muted-foreground'}`}>
              {atRisk}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* ── Two-column layout: Radar + Cognitive Health ──────── */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* Radar chart */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-primary" />
              Mastery Radar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <MasteryRadarChart mastery={mastery} height={300} />
          </CardContent>
        </Card>

        {/* Cognitive health bars */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              Cognitive Health
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <CognitiveHealthBar value={avgMastery} label="Overall Mastery" />
            <CognitiveHealthBar value={avgDecay} label="Knowledge Retention" />
            <CognitiveHealthBar value={avgAccuracy} label="Answer Accuracy" />
            <CognitiveHealthBar
              value={stats.total_skills > 0 ? aboveMastery / stats.total_skills : 0}
              label="Skills Mastered (≥ threshold)"
            />

            {/* Skill status summary */}
            <div className="pt-2 border-t space-y-2">
              <p className="text-xs font-medium text-muted-foreground">Skill Status Distribution</p>
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="secondary" className="text-xs bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  {aboveMastery} mastered
                </Badge>
                <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                  {mastery.filter((m) => m.status === 'at').length} at target
                </Badge>
                <Badge variant="secondary" className="text-xs bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200">
                  {mastery.filter((m) => m.status === 'below').length} below
                </Badge>
                {notStarted > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {notStarted} not started
                  </Badge>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Skill Velocity Table ─────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Zap className="h-4 w-4 text-primary" />
            Skill Velocity Profile
          </CardTitle>
        </CardHeader>
        <CardContent>
          {mastery.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">No data yet</p>
          ) : (
            <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
              {[...mastery]
                .sort((a, b) => b.mastery - a.mastery)
                .map((s) => {
                  const vel = velocityLabel(s);
                  return (
                    <div
                      key={s.skill_name}
                      className="flex items-center gap-2 cursor-pointer rounded-md px-2 py-1.5 hover:bg-muted/50 transition-colors"
                      onClick={() => onPracticeSkill?.(s.skill_name)}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate font-medium">{s.skill_name}</p>
                        <div className="flex items-center gap-2 mt-0.5">
                          <Progress value={s.mastery * 100} className="h-1.5 flex-1" />
                          <span className="text-xs text-muted-foreground w-8 text-right">
                            {(s.mastery * 100).toFixed(0)}%
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-0.5 shrink-0 w-24">
                        <span className={`text-xs font-medium ${vel.color}`}>{vel.label}</span>
                        <span className="text-[10px] text-muted-foreground">
                          {s.correct_count}/{s.attempt_count} correct
                        </span>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── PCO Risk Detail ──────────────────────────────────── */}
      {pco_skills.length > 0 && (
        <Card className="border-red-200 dark:border-red-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium flex items-center gap-2 text-red-600 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              At-Risk Skills (PCO Detected)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {pco_skills.map((s) => (
                <div
                  key={s.skill_name}
                  className="flex items-center justify-between rounded-md border border-red-100 dark:border-red-900 bg-red-50 dark:bg-red-950/20 px-3 py-2 cursor-pointer hover:bg-red-100 dark:hover:bg-red-950/40 transition-colors"
                  onClick={() => onPracticeSkill?.(s.skill_name)}
                >
                  <div>
                    <p className="text-sm font-medium">{s.skill_name}</p>
                    <p className="text-xs text-muted-foreground">{s.why}</p>
                  </div>
                  <Badge variant="destructive" className="text-xs shrink-0">
                    {s.failure_streak}× streak
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
