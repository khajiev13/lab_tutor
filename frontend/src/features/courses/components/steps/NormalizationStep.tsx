import { AlertCircle, ArrowRight } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { NormalizationDashboard } from "@/features/normalization/components/NormalizationDashboard";
import { useCourseDetail } from "../../context/CourseDetailContext";

export function NormalizationStep() {
  const { course, courseId, goToNext } = useCourseDetail();

  if (!course) return null;

  const disabled = course.extraction_status !== "finished";

  return (
    <div className="space-y-4">
      {disabled && (
        <Alert className="bg-muted/50">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Extraction required</AlertTitle>
          <AlertDescription>
            Run extraction first so the concept bank is populated for this
            course.
          </AlertDescription>
        </Alert>
      )}

      <NormalizationDashboard courseId={courseId} disabled={disabled} />

      {!disabled && (
        <div className="flex justify-end pt-2">
          <Button onClick={goToNext} variant="outline" className="gap-2">
            Continue to Book Selection
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
