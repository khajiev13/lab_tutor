import { useData } from "@/features/arcd-agent/context/DataContext";
import { ScheduleTab } from "@/features/arcd-agent/components/schedule-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function SchedulePage() {
  const { student, skills, refreshData } = useData();

  if (!student) return <NoData />;

  return <ScheduleTab student={student} skills={skills} onRefresh={refreshData} />;
}
