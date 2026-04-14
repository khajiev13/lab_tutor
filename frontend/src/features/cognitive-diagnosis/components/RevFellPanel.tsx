import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  AlertTriangle,
  Clock,
  Flame,
  Loader2,
  Smile,
  Zap,
} from 'lucide-react';
import type { ReviewResponse, PCOSkill } from '../api';

interface RevFellPanelProps {
  review: ReviewResponse | null;
  pcoSkillsFromPortfolio: PCOSkill[];
  loading?: boolean;
  onPracticeSkill?: (skillName: string) => void;
}

export function RevFellPanel({
  review,
  pcoSkillsFromPortfolio,
  loading,
  onPracticeSkill,
}: RevFellPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mr-2" />
        <span className="text-sm text-muted-foreground">Running RevFell analysis…</span>
      </div>
    );
  }

  // Merge: prefer full review data, fall back to portfolio PCO list
  const pcoSkills = review?.pco_skills ?? pcoSkillsFromPortfolio;
  const reviewQueue = review?.review_queue ?? [];
  const emotionalState = review?.emotional_state ?? 'engaged';

  return (
    <div className="space-y-4">
      {/* PCO Detection */}
      <Card className={pcoSkills.length > 0 ? 'border-orange-200 dark:border-orange-800' : ''}>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-orange-500" />
            PCO Detection — Prior Correct to Overclaim
            {pcoSkills.length > 0 && (
              <Badge variant="destructive" className="ml-1 text-xs px-1.5">
                {pcoSkills.length} at risk
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pcoSkills.length === 0 ? (
            <div className="flex items-center gap-2 py-3 text-sm text-green-700 dark:text-green-400">
              <Smile className="h-4 w-4" />
              No PCO skills detected — retention looks healthy!
            </div>
          ) : (
            <div className="space-y-3">
              {pcoSkills.map((s) => (
                <PCOCard key={s.skill_name} skill={s} onPractice={onPracticeSkill} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Fast Review Queue */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <Zap className="h-4 w-4 text-blue-500" />
            Fast Review Queue
          </CardTitle>
        </CardHeader>
        <CardContent>
          {reviewQueue.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No urgent reviews right now. Keep practising!
            </p>
          ) : (
            <div className="space-y-2">
              {reviewQueue.slice(0, 8).map((item, i) => {
                const urgency = typeof item.urgency === 'number' ? item.urgency : 0;
                return (
                  <div
                    key={item.skill_name}
                    className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/50"
                  >
                    <span className="text-xs font-mono text-muted-foreground w-4 shrink-0">
                      {i + 1}.
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate">{item.skill_name}</p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <Progress
                          value={urgency * 100}
                          className="h-1 flex-1"
                        />
                        <span className="text-xs text-muted-foreground tabular-nums w-8 shrink-0">
                          {(urgency * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                    {onPracticeSkill && (
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-xs h-6 px-2 shrink-0"
                        onClick={() => onPracticeSkill(item.skill_name)}
                      >
                        Review
                      </Button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Emotional State + Teaching Strategy */}
      {review && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Smile className="h-4 w-4 text-purple-500" />
                Emotional State
              </CardTitle>
            </CardHeader>
            <CardContent>
              <EmotionalStateBadge state={emotionalState} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2">
                <Flame className="h-4 w-4 text-amber-500" />
                Teaching Strategy
              </CardTitle>
            </CardHeader>
            <CardContent>
              {Object.keys(review.teaching_strategy ?? {}).length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Standard pacing — continue current approach.
                </p>
              ) : (
                <div className="space-y-1">
                  {Object.entries(review.teaching_strategy).map(([k, v]) => (
                    <div key={k} className="flex justify-between text-xs gap-2">
                      <span className="text-muted-foreground capitalize">{k.replace(/_/g, ' ')}</span>
                      <span className="font-medium text-right">{String(v)}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Last updated note */}
      {review?.review_queue && (
        <div className="flex items-center gap-1 text-xs text-muted-foreground">
          <Clock className="h-3 w-3" />
          <span>RevFell analysis based on your current interaction history</span>
        </div>
      )}
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────────────

function PCOCard({
  skill,
  onPractice,
}: {
  skill: PCOSkill;
  onPractice?: (name: string) => void;
}) {
  const riskPct = Math.round(skill.decay_risk * 100);
  const masteryPct = Math.round(skill.mastery * 100);

  return (
    <div className="p-3 rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <span className="font-medium text-sm">{skill.skill_name}</span>
        <div className="flex gap-1 shrink-0">
          <Badge variant="outline" className="text-xs text-orange-600 border-orange-300">
            {riskPct}% decay risk
          </Badge>
          {skill.failure_streak > 0 && (
            <Badge variant="outline" className="text-xs text-red-600 border-red-300">
              {skill.failure_streak}× streak
            </Badge>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <span>Mastery: <strong>{masteryPct}%</strong></span>
        <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full rounded-full bg-orange-500"
            style={{ width: `${masteryPct}%` }}
          />
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{skill.why}</p>

      {onPractice && (
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs mt-1"
          onClick={() => onPractice(skill.skill_name)}
        >
          Practice now →
        </Button>
      )}
    </div>
  );
}

const EMOTIONAL_STATES: Record<string, { label: string; color: string; emoji: string }> = {
  engaged: { label: 'Engaged', color: 'text-green-600', emoji: '🟢' },
  struggling: { label: 'Struggling', color: 'text-orange-600', emoji: '🟡' },
  frustrated: { label: 'Frustrated', color: 'text-red-600', emoji: '🔴' },
  bored: { label: 'Bored', color: 'text-blue-600', emoji: '🔵' },
  confused: { label: 'Confused', color: 'text-purple-600', emoji: '🟣' },
};

function EmotionalStateBadge({ state }: { state: string }) {
  const cfg = EMOTIONAL_STATES[state] ?? { label: state, color: 'text-muted-foreground', emoji: '⚪' };
  return (
    <div className="flex items-center gap-2">
      <span className="text-lg">{cfg.emoji}</span>
      <span className={`text-sm font-medium capitalize ${cfg.color}`}>{cfg.label}</span>
    </div>
  );
}
