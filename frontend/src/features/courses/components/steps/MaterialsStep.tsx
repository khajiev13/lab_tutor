import { Loader2, AlertCircle, CheckCircle2, ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Progress } from "@/components/ui/progress";
import { FileUpload } from "@/components/FileUpload";
import { CourseMaterialsTable } from "@/components/CourseMaterialsTable";
import { presentationsApi } from "@/features/courses/api";
import { useCourseDetail } from "@/features/courses/context/CourseDetailContext";
import { toast } from "sonner";

export function MaterialsStep() {
  const {
    course,
    courseId,
    extractionProgress,
    onProgressChange,
    onFilesChange,
    refreshTrigger,
    triggerRefresh,
    refreshCourse,
    embeddingStatus,
    goToNext,
    canNavigateToStep,
  } = useCourseDetail();

  if (!course) return null;

  const isExtractionInProgress = course.extraction_status === "in_progress";
  const handleUpload = async (files: File[]) => {
    if (course.extraction_status === "in_progress") {
      toast.error("Cannot modify files while extraction is in progress");
      return;
    }
    await presentationsApi.upload(course.id, files);
    triggerRefresh();
    await refreshCourse();
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Course Materials</CardTitle>
            <CardDescription>
              Upload presentations and documents, then run extraction to build
              your concept bank.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div
          className={
            isExtractionInProgress
              ? "opacity-50 pointer-events-none"
              : ""
          }
        >
          <FileUpload onUpload={handleUpload} disabled={isExtractionInProgress} />
        </div>

        {isExtractionInProgress && (
          <>
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-blue-500 font-medium flex items-center">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing course materials...
                </span>
                {extractionProgress?.total ? (
                  <span className="text-muted-foreground tabular-nums">
                    Done {extractionProgress.terminal}/
                    {extractionProgress.total}
                    {extractionProgress.failed > 0
                      ? ` • Failed ${extractionProgress.failed}`
                      : ""}
                  </span>
                ) : (
                  <span className="text-muted-foreground">Please wait</span>
                )}
              </div>
              <Progress
                value={
                  extractionProgress?.total
                    ? extractionProgress.value
                    : undefined
                }
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                This process may take a few minutes depending on the size of
                your presentations.
              </p>
            </div>
            <Alert className="bg-muted/50">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>File Management Locked</AlertTitle>
              <AlertDescription>
                You cannot upload or delete files while data extraction is in
                progress.
              </AlertDescription>
            </Alert>
          </>
        )}

        {course.extraction_status === "failed" && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Extraction Failed</AlertTitle>
            <AlertDescription>
              There was an error processing your course materials. Please check
              your files and try again.
            </AlertDescription>
          </Alert>
        )}

        {course.extraction_status === "finished" && (
          <Alert className="border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20">
            <CheckCircle2 className="h-4 w-4 text-green-600" />
            <AlertTitle>Extraction complete</AlertTitle>
            <AlertDescription>
              Your course materials were processed successfully. Continue to the
              next step to choose books.
            </AlertDescription>
          </Alert>
        )}

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-medium">Files</h3>
            {isExtractionInProgress && (
              <span className="text-xs text-muted-foreground">Updating…</span>
            )}
          </div>
          <CourseMaterialsTable
            courseId={courseId}
            refreshTrigger={refreshTrigger}
            disabled={isExtractionInProgress}
            poll={isExtractionInProgress}
            pollIntervalMs={10_000}
            onFilesChange={onFilesChange}
            onProgressChange={onProgressChange}
            embeddingStatus={embeddingStatus}
          />
        </div>

        {/* Continue CTA */}
        {canNavigateToStep(3) && (
          <div className="flex justify-end pt-2">
            <Button onClick={goToNext} className="gap-2">
              Continue to Books
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
