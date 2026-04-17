import { useData } from "@/features/arcd-agent/context/DataContext";
import { useTwin } from "@/features/arcd-agent/context/TwinContext";
import { UnifiedTab } from "@/features/arcd-agent/components/unified-tab";
import { Badge } from "@/components/ui/badge";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function StudentPage() {
  const { student, currentDataset, skills, activeDatasetId } = useData();
  const { twinData, twinMatched, twinLoading } = useTwin();

  if (!student || !currentDataset) return <NoData />;

  const allStudents = currentDataset.students;

  return (
    <div className="space-y-4">
      {/* ── Header bar: twin status ── */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          {twinLoading && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" />
              Loading twin…
            </span>
          )}
          {!twinLoading && twinMatched && (
            <Badge variant="outline" className="text-xs text-emerald-600 dark:text-emerald-400 border-emerald-500/40">
              Twin active · {student.uid}
            </Badge>
          )}
          {!twinLoading && !twinMatched && (
            <Badge variant="outline" className="text-xs text-amber-600 dark:text-amber-400 border-amber-500/40">
              Twin not yet available
            </Badge>
          )}
        </div>
      </div>

      <UnifiedTab
        student={student}
        modelInfo={currentDataset.model_info}
        skills={skills}
        datasetId={activeDatasetId}
        twinData={twinData}
        viewMode="student"
        allStudents={allStudents}
      />
    </div>
  );
}
