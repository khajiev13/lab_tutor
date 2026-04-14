import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { BookAnalysisTab } from "@/features/book-selection";
import { useCourseDetail } from "../../context/CourseDetailContext";

export function AnalysisStep() {
  const { course, courseId, goToNext } = useCourseDetail();

  if (!course) return null;

  const disabled = course.extraction_status !== "finished";

  return (
    <div className="space-y-4">
      <BookAnalysisTab courseId={courseId} disabled={disabled} />

      {!disabled && (
        <div className="flex justify-end pt-2">
          <Button onClick={goToNext} variant="outline" className="gap-2">
            Continue to Visualization
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
