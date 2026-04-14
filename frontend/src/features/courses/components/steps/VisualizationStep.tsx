import { BookVisualizationTab } from "@/features/book-selection";
import { useCourseDetail } from "../../context/CourseDetailContext";

export function VisualizationStep() {
  const { course, courseId } = useCourseDetail();

  if (!course) return null;

  const disabled = course.extraction_status !== "finished";

  return <BookVisualizationTab courseId={courseId} disabled={disabled} />;
}
