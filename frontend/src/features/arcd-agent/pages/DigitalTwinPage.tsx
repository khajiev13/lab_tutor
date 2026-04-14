import { useData } from "@/features/arcd-agent/context/DataContext";
import { useTwin } from "@/features/arcd-agent/context/TwinContext";
import { TwinViewerTab } from "@/features/arcd-agent/components/twin-viewer-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function DigitalTwinPage() {
  const { student, skills, currentDataset, viewMode, setSelectedUid } = useData();
  const { twinData } = useTwin();
  const allStudents = currentDataset?.students ?? [];

  if (!student || !currentDataset) return <NoData />;

  return (
    <TwinViewerTab
      student={student}
      skills={skills}
      datasetId={currentDataset.id}
      twinData={twinData}
      viewMode={viewMode}
      allStudents={allStudents}
      setSelectedUid={setSelectedUid}
    />
  );
}
