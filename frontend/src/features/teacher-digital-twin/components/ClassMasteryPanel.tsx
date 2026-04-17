/** Class Mastery panel — Feature 3 */
import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Loader2, Users, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { ClassMasteryResponse, StudentMasterySummary } from '../api';

type MasteryTier = 'high' | 'medium' | 'low';

function getMasteryTier(avgMastery: number): MasteryTier {
  if (avgMastery >= 0.7) return 'high';
  if (avgMastery >= 0.4) return 'medium';
  return 'low';
}

const tierColor: Record<MasteryTier, string> = {
  high: 'bg-green-100 text-green-700 border-green-300',
  medium: 'bg-blue-100 text-blue-700 border-blue-300',
  low: 'bg-red-100 text-red-700 border-red-300',
};

function computeStdDev(students: StudentMasterySummary[], mean: number): number {
  if (students.length < 2) return 0;
  const variance =
    students.reduce((sum, s) => sum + Math.pow(s.avg_mastery - mean, 2), 0) / students.length;
  return Math.sqrt(variance);
}

export function ClassMasteryPanel({ courseId }: { courseId: number }) {
  const [data, setData] = useState<ClassMasteryResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const stdDev = useMemo(
    () => (data ? computeStdDev(data.students, data.class_avg_mastery) : 0),
    [data],
  );

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
          {loading ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" />
          )}
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
                <p className="text-2xl font-bold tabular-nums">{(stdDev * 100).toFixed(0)}%</p>
                <p className="text-xs text-muted-foreground">Std Dev</p>
              </div>
            </div>

            {/* At-risk banner */}
            {data.at_risk_count > 0 && (
              <div className="p-2 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                ⚠ {data.at_risk_count} student{data.at_risk_count !== 1 ? 's' : ''} at risk
              </div>
            )}

            {/* Per-student rows */}
            <div className="space-y-2">
              {data.students.map((s) => {
                const tier = getMasteryTier(s.avg_mastery);
                return (
                  <div
                    key={s.user_id}
                    className="p-3 border rounded-lg hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{s.full_name}</span>
                        <Badge className={`text-xs ${tierColor[tier]}`}>{tier}</Badge>
                        {s.at_risk && (
                          <Badge className="text-xs bg-red-100 text-red-700 border-red-300">
                            at risk
                          </Badge>
                        )}
                      </div>
                      <span className="text-sm font-bold tabular-nums">
                        {(s.avg_mastery * 100).toFixed(0)}%
                      </span>
                    </div>
                    <Progress value={s.avg_mastery * 100} className="h-1.5" />
                    <div className="flex gap-3 mt-1">
                      <span className="text-xs text-muted-foreground">
                        {s.mastered_count}/{s.selected_skill_count} mastered
                      </span>
                      {s.struggling_count > 0 && (
                        <span className="text-xs text-red-500">
                          {s.struggling_count} struggling
                        </span>
                      )}
                      {s.pco_count > 0 && (
                        <span className="text-xs text-orange-500">{s.pco_count} PCO</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
