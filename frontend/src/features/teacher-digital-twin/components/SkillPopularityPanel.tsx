/** Skill Popularity panel — Feature 2 */
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, BarChart3, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { SkillPopularityItem, SkillPopularityResponse } from '../api';

export function SkillPopularityPanel({ courseId }: { courseId: number }) {
  const [data, setData] = useState<SkillPopularityResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await teacherTwinApi.getSkillPopularity(courseId);
      setData(resp.data);
    } catch {
      toast.error('Failed to load skill popularity data');
    } finally {
      setLoading(false);
    }
  };

  const SkillRow = ({ skill }: { skill: SkillPopularityItem }) => {
    const popularityRatio =
      data && data.total_students > 0 ? skill.selection_count / data.total_students : 0;

    return (
      <div className="flex items-center justify-between py-2 border-b last:border-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted-foreground w-5">{skill.rank}.</span>
          <span className="text-sm">{skill.skill_name}</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full"
              style={{ width: `${popularityRatio * 100}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-10 text-right">
            {skill.selection_count} / {data?.total_students}
          </span>
        </div>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-blue-500" />
          Skill Popularity (by student selection)
        </CardTitle>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {data ? '' : ' Load'}
        </Button>
      </CardHeader>
      <CardContent>
        {!data && !loading && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Click Load to see which skills students are choosing most and least.
          </p>
        )}
        {loading && (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
        {data && (
          <div className="grid md:grid-cols-2 gap-4 mt-2">
            <div>
              <div className="flex items-center gap-1 mb-2">
                <TrendingUp className="h-3.5 w-3.5 text-green-600" />
                <span className="text-xs font-semibold text-green-700">Most Studied</span>
                <Badge variant="outline" className="ml-auto text-xs">
                  {data.most_popular.length}
                </Badge>
              </div>
              {data.most_popular.map((s) => (
                <SkillRow key={s.skill_name} skill={s} />
              ))}
            </div>
            <div>
              <div className="flex items-center gap-1 mb-2">
                <TrendingDown className="h-3.5 w-3.5 text-orange-500" />
                <span className="text-xs font-semibold text-orange-600">Least Studied</span>
                <Badge variant="outline" className="ml-auto text-xs">
                  {data.least_popular.length}
                </Badge>
              </div>
              {data.least_popular.map((s) => (
                <SkillRow key={s.skill_name} skill={s} />
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
