import { cn } from '@/lib/utils';
import type { SkillMastery } from '../api';

interface MasteryBarProps {
  skill: SkillMastery;
  compact?: boolean;
}

const STATUS_CONFIG = {
  not_started: { label: 'Not Started', color: 'bg-muted', text: 'text-muted-foreground' },
  below: { label: 'Learning', color: 'bg-orange-500', text: 'text-orange-700 dark:text-orange-400' },
  at: { label: 'In Progress', color: 'bg-blue-500', text: 'text-blue-700 dark:text-blue-400' },
  above: { label: 'Mastered', color: 'bg-green-500', text: 'text-green-700 dark:text-green-400' },
} as const;

export function MasteryBar({ skill, compact = false }: MasteryBarProps) {
  const cfg = STATUS_CONFIG[skill.status] ?? STATUS_CONFIG.not_started;
  const pct = Math.round(skill.mastery * 100);
  const decayPct = Math.round(skill.decay * 100);

  if (compact) {
    return (
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-xs font-medium truncate flex-1">{skill.skill_name}</span>
        <div className="flex items-center gap-1 shrink-0">
          <div className="w-16 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={cn('h-full rounded-full transition-all', cfg.color)}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className="text-xs tabular-nums w-8 text-right">{pct}%</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium truncate flex-1 mr-2">{skill.skill_name}</span>
        <span className={cn('text-xs shrink-0', cfg.text)}>{cfg.label}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden relative">
          {/* Mastery bar */}
          <div
            className={cn('h-full rounded-full transition-all duration-500', cfg.color)}
            style={{ width: `${pct}%` }}
          />
          {/* Decay overlay — indicates retention */}
          {skill.status !== 'not_started' && (
            <div
              className="absolute top-0 left-0 h-full bg-black/10 dark:bg-white/10 rounded-full"
              style={{ width: `${100 - decayPct}%`, marginLeft: `${decayPct}%` }}
              title={`Retention: ${decayPct}%`}
            />
          )}
        </div>
        <span className="text-xs tabular-nums w-10 text-right text-muted-foreground">
          {pct}%
        </span>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{skill.attempt_count} attempts</span>
        <span>Retention: {decayPct}%</span>
      </div>
    </div>
  );
}
