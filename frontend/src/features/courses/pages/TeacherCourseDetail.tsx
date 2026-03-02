import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, LogIn, LogOut } from 'lucide-react';
import { toast } from 'sonner';

import { useAuth } from '@/features/auth/context/AuthContext';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardHeader,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { StepContent } from '@/components/ui/stepper';
import { coursesApi } from '../api';
import {
  CourseDetailProvider,
  useCourseDetail,
} from '../context/CourseDetailContext';
import { CourseHeader } from '../components/CourseHeader';
import { CourseStepperHeader } from '../components/CourseStepperHeader';
import { MaterialsStep } from '../components/steps/MaterialsStep';
import { NormalizationStep } from '../components/steps/NormalizationStep';
import { BookSelectionStep } from '../components/steps/BookSelectionStep';

/* Lazy-load heavy steps */
const AnalysisStep = lazy(() =>
  import('../components/steps/AnalysisStep').then((m) => ({
    default: m.AnalysisStep,
  }))
);
const VisualizationStep = lazy(() =>
  import('../components/steps/VisualizationStep').then((m) => ({
    default: m.VisualizationStep,
  }))
);

function StepSkeleton() {
  return (
    <div className="space-y-4 pt-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-64 w-full" />
    </div>
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { coursesApi, presentationsApi } from '../api';
import type { Course, CourseEmbeddingStatusResponse, ExtractionStatus, EmbeddingStatus } from '../types';
import { FileUpload } from '@/components/FileUpload';
import { CourseMaterialsTable } from '@/components/CourseMaterialsTable';
import { NormalizationDashboard } from '@/features/normalization/components/NormalizationDashboard';
import { BookSelectionDashboard, BookAnalysisTab, BookVisualizationTab } from '@/features/book-selection';

export default function TeacherCourseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [course, setCourse] = useState<Course | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isExtracting, setIsExtracting] = useState(false);
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [isEnrollmentLoading, setIsEnrollmentLoading] = useState(false);
  const [presentationCount, setPresentationCount] = useState(0);
  const [activeTab, setActiveTab] = useState('materials');
  const [embeddingStatus, setEmbeddingStatus] = useState<CourseEmbeddingStatusResponse | null>(null);
  const [extractionProgress, setExtractionProgress] = useState<{
    total: number;
    processed: number;
    failed: number;
    terminal: number;
    value: number;
    allTerminal: boolean;
  } | null>(null);
  const handleProgressChange = useCallback(
    (stats: {
      total: number;
      processed: number;
      failed: number;
      terminal: number;
      value: number;
      allTerminal: boolean;
    }) => {
      setExtractionProgress((prev) => {
        if (!prev) return stats;
        const isSame =
          prev.total === stats.total &&
          prev.processed === stats.processed &&
          prev.failed === stats.failed &&
          prev.terminal === stats.terminal &&
          prev.value === stats.value &&
          prev.allTerminal === stats.allTerminal;
        return isSame ? prev : stats;
      });
    },
    []
  );
}

/* ── Teacher content ─────────────────────────────────────────── */

function TeacherContent() {
  const { activeStep, isLoading, course } = useCourseDetail();

  if (isLoading || !course) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <>
      <CourseHeader />
      <CourseStepperHeader />

      <StepContent activeIndex={activeStep} index={0}>
        <MaterialsStep />
      </StepContent>

      <StepContent activeIndex={activeStep} index={1}>
        <NormalizationStep />
      </StepContent>

      <StepContent activeIndex={activeStep} index={2}>
        <BookSelectionStep />
      </StepContent>

      <Suspense fallback={<StepSkeleton />}>
        <StepContent activeIndex={activeStep} index={3}>
          <AnalysisStep />
        </StepContent>
      </Suspense>

      <Suspense fallback={<StepSkeleton />}>
        <StepContent activeIndex={activeStep} index={4}>
          <VisualizationStep />
        </StepContent>
      </Suspense>
    </>
  );
}

/* ── Student content ─────────────────────────────────────────── */

function StudentContent({ courseId }: { courseId: number }) {
  const [isEnrolled, setIsEnrolled] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const checkEnrollment = useCallback(async () => {
    try {
      const enrollment = await coursesApi.getEnrollment(courseId);
      setIsEnrolled(!!enrollment);
    } catch {
      /* ignore */
    }
  }, [courseId]);

  useEffect(() => {
    checkEnrollment();
  }, [checkEnrollment]);

  const handleJoin = async () => {
    setIsLoading(true);
    try {
      await coursesApi.join(courseId);
      setIsEnrolled(true);
      toast.success('Successfully joined the course!');
    } catch {
      toast.error('Failed to join course');
    } finally {
      setIsLoading(false);
    }
  };

  const handleLeave = async () => {
    setIsLoading(true);
    try {
      await coursesApi.leave(courseId);
      setIsEnrolled(false);
      toast.success('Successfully left the course');
    } catch {
      toast.error('Failed to leave course');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex justify-end">
          <Button
            onClick={isEnrolled ? handleLeave : handleJoin}
            disabled={isLoading}
            variant={isEnrolled ? 'destructive' : 'default'}
          >
            {isLoading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : isEnrolled ? (
              <>
                <LogOut className="mr-2 h-4 w-4" />
                Leave Course
              </>
            ) : (
              <>
                <LogIn className="mr-2 h-4 w-4" />
                Join Course
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          {isEnrolled
            ? 'You are enrolled in this course.'
            : 'Join this course to access materials and assessments.'}
        </p>
      </CardContent>
    </Card>
  );
}

/* ── Page ─────────────────────────────────────────────────────── */

export default function TeacherCourseDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();

  const courseId = Number(id);
  if (!id || isNaN(courseId)) {
    navigate('/courses');
    return null;
  }

  return (
    <CourseDetailProvider courseId={courseId}>
      <div className="space-y-6">
        <Button
          variant="ghost"
          className="pl-0 hover:bg-transparent hover:text-primary"
          onClick={() => navigate('/courses')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Courses
        </Button>

        {user?.role === 'teacher' ? (
          <TeacherContent />
        ) : (
          <StudentContent courseId={courseId} />
        )}
      </div>
    </CourseDetailProvider>

      <Card>
        <CardHeader>
          <div className="flex justify-between items-start">
            <div>
              <CardTitle className="text-2xl">{course.title}</CardTitle>
              <CardDescription className="text-base mt-2">
                {course.description || 'No description provided.'}
              </CardDescription>
            </div>
            {canStartExtraction && (
              <Button onClick={handleStartExtraction} disabled={isExtracting}>
                {isExtracting ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Start Data Extraction
              </Button>
            )}
            {user?.role === 'teacher' && course.extraction_status === 'finished' && (
              <Button
                variant="secondary"
                onClick={() => navigate(`/courses/${course.id}/graph`)}
              >
                <GitBranch className="mr-2 h-4 w-4" />
                View knowledge graph
              </Button>
            )}
            {user?.role === 'student' && (
              <Button 
                onClick={isEnrolled ? handleLeave : handleJoin} 
                disabled={isEnrollmentLoading}
                variant={isEnrolled ? "destructive" : "default"}
              >
                {isEnrollmentLoading ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : isEnrolled ? (
                  <>
                    <LogOut className="mr-2 h-4 w-4" />
                    Leave Course
                  </>
                ) : (
                  <>
                    <LogIn className="mr-2 h-4 w-4" />
                    Join Course
                  </>
                )}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center text-sm text-muted-foreground">
            <span className="font-medium text-foreground mr-2">Created:</span>
            {new Date(course.created_at).toLocaleDateString()}
          </div>
          
          {user?.role === 'teacher' && isExtractionInProgress && (
            <div className="mt-6 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-blue-500 font-medium flex items-center">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing course materials...
                </span>
                {extractionProgress?.total ? (
                  <span className="text-muted-foreground tabular-nums">
                    Done {extractionProgress.terminal}/{extractionProgress.total}
                    {extractionProgress.failed > 0 ? ` • Failed ${extractionProgress.failed}` : ""}
                  </span>
                ) : (
                  <span className="text-muted-foreground">Please wait</span>
                )}
              </div>
              <Progress
                value={extractionProgress?.total ? extractionProgress.value : undefined}
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                This process may take a few minutes depending on the size of your presentations.
              </p>
            </div>
          )}

          {user?.role === 'teacher' && course.extraction_status === 'failed' && (
            <Alert variant="destructive" className="mt-6">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Extraction Failed</AlertTitle>
              <AlertDescription>
                There was an error processing your course materials. Please check your files and try again.
              </AlertDescription>
            </Alert>
          )}

          {user?.role === 'teacher' && course.extraction_status === 'finished' && (
            <Alert className="mt-6 border-green-500 text-green-600 bg-green-50 dark:bg-green-950/20">
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <AlertTitle>Extraction complete</AlertTitle>
              <AlertDescription>
                Your course materials were processed successfully. Next, pick a book to build the knowledge graph from.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {user?.role === 'teacher' && (
        <Tabs defaultValue="materials" className="w-full" onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="materials">Materials</TabsTrigger>
            <TabsTrigger value="normalization">Concept normalization</TabsTrigger>
            <TabsTrigger value="book-selection">Book Selection</TabsTrigger>
            <TabsTrigger value="analysis">Book Analysis</TabsTrigger>
            <TabsTrigger value="visualization">Book Visualization</TabsTrigger>
          </TabsList>

          <TabsContent value="materials">
            <Card>
              <CardHeader>
                <CardTitle>Course Materials</CardTitle>
                <CardDescription>
                  Manage presentations and documents for this course.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className={isExtractionInProgress ? "opacity-50 pointer-events-none" : ""}>
                  <FileUpload onUpload={handleUpload} disabled={isExtractionInProgress} />
                </div>
                
                {isExtractionInProgress && (
                  <Alert className="bg-muted/50">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>File Management Locked</AlertTitle>
                    <AlertDescription>
                      You cannot upload or delete files while data extraction is in progress.
                    </AlertDescription>
                  </Alert>
                )}

                <div className="space-y-6">
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium">Files</h3>
                      {isExtractionInProgress && (
                        <span className="text-xs text-muted-foreground">Updating…</span>
                      )}
                    </div>
                    <CourseMaterialsTable
                      courseId={course.id}
                      refreshTrigger={refreshTrigger}
                      disabled={isExtractionInProgress}
                      poll={isExtractionInProgress}
                      pollIntervalMs={pollIntervalMs}
                      onFilesChange={handleFilesChange}
                      onProgressChange={handleProgressChange}
                      embeddingStatus={embeddingStatus}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="normalization">
            {course.extraction_status !== 'finished' && (
              <Alert className="mb-4 bg-muted/50">
                <AlertCircle className="h-4 w-4" />
                <AlertTitle>Extraction required</AlertTitle>
                <AlertDescription>
                  Run extraction first so the concept bank is populated for this course.
                </AlertDescription>
              </Alert>
            )}
            <NormalizationDashboard
              courseId={course.id}
              disabled={course.extraction_status !== 'finished'}
            />
          </TabsContent>

          <TabsContent value="book-selection">
            <BookSelectionDashboard
              courseId={course.id}
              disabled={course.extraction_status !== 'finished'}
            />
          </TabsContent>

          <TabsContent value="analysis">
            <BookAnalysisTab
              courseId={course.id}
              disabled={course.extraction_status !== 'finished'}
            />
          </TabsContent>

          <TabsContent value="visualization">
            <BookVisualizationTab
              courseId={course.id}
              disabled={course.extraction_status !== 'finished'}
            />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
