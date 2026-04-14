import { useData } from "@/features/arcd-agent/context/DataContext";
import { useTwin } from "@/features/arcd-agent/context/TwinContext";
import { JourneyMapTab } from "@/features/arcd-agent/components/journey-map-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function JourneyPage() {
  const { student, skills } = useData();
  const { twinData } = useTwin();

  if (!student) return <NoData />;

  return <JourneyMapTab student={student} skills={skills} twinData={twinData} />;
}
