import { useData } from "@/features/arcd-agent/context/DataContext";
import { QuizLabTab } from "@/features/arcd-agent/components/quiz-lab-tab";

function NoData() {
  return (
    <div className="flex items-center justify-center h-64 text-muted-foreground">
      No student data available.
    </div>
  );
}

export default function QuizLabPage() {
  const { student, skills } = useData();

  if (!student) return <NoData />;

  return <QuizLabTab student={student} skills={skills} />;
}
