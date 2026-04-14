/** Class Mastery panel — Feature 3 */
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Loader2, Users, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { ClassMasteryResponse, StudentMasterySummary } from '../api';

const tierColor: Record<StudentMasterySummary['mastery_tier'], string> = {
  high: 'bg-green-100 text-green-700 border-green-300',
  medium: 'bg-blue-100 text-blue-700 border-blue-300',
  low: 'bg-red-100 text-red-700 border-red-300',
};

export function ClassMasteryPanel({ courseId }: { courseId: number }) {
  const [data, setData] = useState<ClassMasteryResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await teacherTwinApi.getClassMastery(courseId);
      setData(resp.data);
    } catch {
      toast.error('Failed to load class mastery');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Users className="h-4 w-4 text-purple-500" />
          Class Mastery Overview
        </CardTitle>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {data ? '' : ' Load'}
        </Button>
      </CardHeader>
      <CardContent>
        {!data && !loading && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Load per-student mastery summaries across all selected skills.
          </p>
        )}
        {loading && (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
        {data && (
          <div className="space-y-4 mt-2">
            {/* Class-level stats */}
            <div className="grid grid-cols-3 gap-3">
              <div className="text-center p-3 bg-muted/50 rounded-lg">
                <p className="text-2xl font-bold tabular-nums">
                  {(data.class_avg_mastery * 100).toFixed(0)}%
                </p>
                <p className="text-xs text-muted-foreground">Class Avg</p>
              </div>
              <div className="text-center p-3 bg-muted/50 rounded-lg">
                <p className="text-2xl font-bold tabular-nums">{data.total_students}</p>
                <p className="text-xs text-muted-foreground">Students</p>
              </div>
              <div className="text-center p-3 bg-muted/50 rounded-lg">
                <p className="text-2xl font-bold tabular-nums">
                  {(data.mastery_std_dev * 100).toFixed(0)}%
                </p>
                <p className="text-xs text-muted-foreground">Std Dev</p>
              </div>
            </div>

            {/* Per-student rows */}
            <div className="space-y-2">
              {data.students.map((s) => (
                <div key={s.user_id} className="p-3 border rounded-lg hover:bg-muted/30 transition-colors">
                  <div className="flex items-center justify-between mb-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">{s.username}</span>
                      <Badge className={`text-xs ${tierColor[s.mastery_tier]}`}>
                        {s.mastery_tier}
                      </Badge>
                    </div>
                    <span className="text-sm font-bold tabular-nums">
                      {(s.avg_mastery * 100).toFixed(0)}%
                    </span>
                  </div>
                  <Progress value={s.avg_mastery * 100} className="h-1.5" />
                  <div className="flex gap-3 mt-1">
                    <span className="text-xs text-muted-foreground">
                      {s.mastered_count}/{s.skill_count} mastered
                    </span>
                    {s.below_threshold_count > 0 && (
                      <span className="text-xs text-red-500">
                        {s.below_threshold_count} below threshold
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
