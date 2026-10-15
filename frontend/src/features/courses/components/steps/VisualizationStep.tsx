import { BookVisualizationTab } from "@/features/book-selection";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";

export function VisualizationStep() {
  const { course, courseId, canNavigateToStep } = useCourseDetail();

  if (!course || !canNavigateToStep(5)) return null;


  return <BookVisualizationTab courseId={courseId} />;
}
