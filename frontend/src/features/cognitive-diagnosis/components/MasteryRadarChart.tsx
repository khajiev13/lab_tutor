import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import type { SkillMastery } from '../api';

interface MasteryRadarChartProps {
  mastery: SkillMastery[];
  height?: number;
}

function truncate(name: string, max = 14): string {
  return name.length > max ? name.slice(0, max - 1) + '…' : name;
}

export function MasteryRadarChart({ mastery, height = 340 }: MasteryRadarChartProps) {
  if (mastery.length === 0) return null;

  // Cap at 12 skills for readability — show highest mastery ones
  const sorted = [...mastery].sort((a, b) => b.mastery - a.mastery);
  const visible = sorted.slice(0, 12);

  const data = visible.map((s) => ({
    skill: truncate(s.skill_name),
    Mastery: Math.round(s.mastery * 100),
    Retention: Math.round(s.decay * 100),
    fullName: s.skill_name,
  }));

  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
        <PolarGrid className="stroke-border/50" />
        <PolarAngleAxis
          dataKey="skill"
          tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
        />
        <PolarRadiusAxis
          angle={90}
          domain={[0, 100]}
          tick={{ fontSize: 9, fill: 'hsl(var(--muted-foreground))' }}
          tickCount={4}
        />
        <Radar
          name="Mastery"
          dataKey="Mastery"
          stroke="hsl(var(--chart-1))"
          fill="hsl(var(--chart-1))"
          fillOpacity={0.35}
          strokeWidth={2}
        />
        <Radar
          name="Retention"
          dataKey="Retention"
          stroke="hsl(var(--chart-2))"
          fill="hsl(var(--chart-2))"
          fillOpacity={0.2}
          strokeWidth={1.5}
          strokeDasharray="4 2"
        />
        <Tooltip
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const p = payload[0]?.payload as { fullName: string; Mastery: number; Retention: number };
            return (
              <div className="rounded-lg border bg-background px-3 py-2 text-xs shadow-md space-y-1">
                <p className="font-semibold text-sm">{p.fullName}</p>
                <p>
                  <span className="text-chart-1">Mastery: </span>
                  <strong>{p.Mastery}%</strong>
                </p>
                <p>
                  <span className="text-chart-2">Retention: </span>
                  <strong>{p.Retention}%</strong>
                </p>
              </div>
            );
          }}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value) => (
            <span style={{ color: 'hsl(var(--foreground))', fontSize: 12 }}>{value}</span>
          )}
        />
      </RadarChart>
    </ResponsiveContainer>
  );
}
