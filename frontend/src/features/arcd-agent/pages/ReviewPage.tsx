import { useData } from "@/features/arcd-agent/context/DataContext";
import { ReviewChatTab } from "@/features/arcd-agent/components/chat-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function ReviewPage() {
  const {
    student,
    currentDataset,
    practiceSkill,
    setPracticeSkill,
    refreshData,
  } = useData();

  if (!student || !currentDataset) return <NoData />;

  return (
    <ReviewChatTab
      student={student}
      datasetId={currentDataset.id}
      practiceSkill={practiceSkill}
      onPracticeConsumed={() => setPracticeSkill(null)}
      onDataChanged={refreshData}
    />
  );
}
