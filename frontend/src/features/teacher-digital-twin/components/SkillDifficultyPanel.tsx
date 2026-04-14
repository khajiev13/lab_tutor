/** Skill Difficulty panel — Feature 1 */
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import { Loader2, TrendingDown, RefreshCw, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { SkillDifficultyItem } from '../api';

export function SkillDifficultyPanel({ courseId }: { courseId: number }) {
  const [skills, setSkills] = useState<SkillDifficultyItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await teacherTwinApi.getSkillDifficulty(courseId);
      setSkills(resp.data.skills);
      setLoaded(true);
    } catch {
      toast.error('Failed to load skill difficulty data');
    } finally {
      setLoading(false);
    }
  };

  const difficultyColor = (d: number) => {
    if (d > 0.7) return 'text-red-600';
    if (d > 0.4) return 'text-orange-500';
    return 'text-green-600';
  };

  const difficultyBadge = (d: number) => {
    if (d > 0.7) return <Badge variant="destructive">Hard</Badge>;
    if (d > 0.4) return <Badge className="bg-orange-100 text-orange-700 border-orange-300">Medium</Badge>;
    return <Badge className="bg-green-100 text-green-700 border-green-300">Easy</Badge>;
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <TrendingDown className="h-4 w-4 text-red-500" />
          Skill Difficulty (based on student mastery)
        </CardTitle>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {loaded ? '' : ' Load'}
        </Button>
      </CardHeader>
      <CardContent>
        {!loaded && !loading && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Click Load to compute perceived difficulty: D(s) = 1 − avg mastery
          </p>
        )}
        {loading && (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
        {loaded && skills.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No skill data available yet. Students need to select skills first.
          </p>
        )}
        {loaded && skills.length > 0 && (
          <div className="space-y-3 mt-2">
            {skills.map((s) => (
              <div key={s.skill_name}>
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    {s.perceived_difficulty > 0.7 && <AlertTriangle className="h-3 w-3 text-red-500" />}
                    <span className="text-sm font-medium">{s.skill_name}</span>
                    {difficultyBadge(s.perceived_difficulty)}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">{s.student_count} students</span>
                    <span className={`text-sm font-bold tabular-nums ${difficultyColor(s.perceived_difficulty)}`}>
                      {(s.perceived_difficulty * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                <Progress
                  value={s.perceived_difficulty * 100}
                  className="h-2"
                />
                <p className="text-xs text-muted-foreground mt-0.5">
                  avg mastery: {(s.avg_mastery * 100).toFixed(0)}%
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
