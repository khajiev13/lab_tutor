/** Student Groups panel — Feature 4 */
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, GitBranch, RefreshCw, ChevronDown, ChevronRight, Users, ArrowRight } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { StudentGroupSummary } from '../api';

function GroupCard({ group, index }: { group: StudentGroupSummary; index: number }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="border-muted">
      <CardContent className="pt-4">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-bold text-primary">
              {index + 1}
            </div>
            <div>
              <p className="text-sm font-medium">
                Group {index + 1}
                <span className="ml-2 text-muted-foreground font-normal text-xs">
                  ({group.student_count} student{group.student_count !== 1 ? 's' : ''})
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                Avg mastery: {(group.avg_group_mastery * 100).toFixed(0)}% · Readiness: {(group.group_readiness * 100).toFixed(0)}%
              </p>
            </div>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground"
          >
            {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          </button>
        </div>

        {/* Skill set chips */}
        <div className="flex flex-wrap gap-1 mt-2">
          {group.skill_set.map((sk) => (
            <Badge key={sk} variant="secondary" className="text-xs font-normal">{sk}</Badge>
          ))}
        </div>

        {expanded && (
          <div className="mt-3 space-y-3 border-t pt-3">
            {/* Students */}
            <div>
              <p className="text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                <Users className="h-3 w-3" /> Students
              </p>
              <div className="flex flex-wrap gap-1">
                {group.student_names.map((n) => (
                  <span key={n} className="text-xs bg-muted px-2 py-0.5 rounded-full">{n}</span>
                ))}
              </div>
            </div>

            {/* Suggested next skills */}
            {group.suggested_next_skills.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1 flex items-center gap-1">
                  <ArrowRight className="h-3 w-3" /> Suggested Path
                </p>
                <div className="flex flex-wrap gap-1">
                  {group.suggested_next_skills.map((sk, i) => (
                    <div key={sk} className="flex items-center gap-1">
                      {i > 0 && <ArrowRight className="h-3 w-3 text-muted-foreground" />}
                      <Badge className="bg-blue-50 text-blue-700 border-blue-200 text-xs font-normal">
                        {sk}
                      </Badge>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function StudentGroupsPanel({ courseId }: { courseId: number }) {
  const [groups, setGroups] = useState<StudentGroupSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const resp = await teacherTwinApi.getStudentGroups(courseId);
      setGroups(resp.data.groups);
      setLoaded(true);
    } catch {
      toast.error('Failed to load student groups');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-indigo-500" />
          Student Groups & Suggested Paths
        </CardTitle>
        <Button size="sm" variant="outline" onClick={load} disabled={loading}>
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          {loaded ? '' : ' Load'}
        </Button>
      </CardHeader>
      <CardContent>
        {!loaded && !loading && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            Groups students by shared skill sets and generates ZPD-calibrated path suggestions per group.
          </p>
        )}
        {loading && (
          <div className="flex items-center justify-center py-6">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        )}
        {loaded && groups.length === 0 && (
          <p className="text-sm text-muted-foreground py-4 text-center">
            No student groups found. Students need to select and lock their skills first.
          </p>
        )}
        {loaded && groups.length > 0 && (
          <div className="space-y-3 mt-2">
            {groups.map((g, i) => (
              <GroupCard key={g.group_id} group={g} index={i} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
