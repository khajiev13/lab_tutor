import { ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { BookAnalysisTab } from "@/features/book-selection";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";

export function AnalysisStep() {
  const { course, courseId, goToNext, canNavigateToStep } = useCourseDetail();

  if (!course || !canNavigateToStep(4)) return null;


  return (
    <div className="space-y-4">
      <BookAnalysisTab courseId={courseId} />

      {canNavigateToStep(5) && (
        <div className="flex justify-end pt-2">
          <Button onClick={goToNext} variant="outline" className="gap-2">
            Continue to Results
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
