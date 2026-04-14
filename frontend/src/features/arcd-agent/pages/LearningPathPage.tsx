import { useNavigate } from "react-router-dom";
import { useData } from "@/features/arcd-agent/context/DataContext";
import { PathGenTab } from "@/features/arcd-agent/components/pathgen-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function LearningPathPage() {
  const { student, skills, currentDataset, setPracticeSkill } = useData();
  const navigate = useNavigate();

  if (!student || !currentDataset) return <NoData />;

  return (
    <PathGenTab
      student={student}
      skills={skills}
      datasetId={currentDataset.id}
      onStartPractice={(skillId, skillName) => {
        setPracticeSkill({ id: skillId, name: skillName });
        navigate("../review");
      }}
    />
  );
}
