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
import { BuildChaptersStep } from '@/features/curriculum-planning/components/BuildChaptersStep';
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
        <BuildChaptersStep />
      </StepContent>

      <StepContent activeIndex={activeStep} index={3}>
        <BookSelectionStep />
      </StepContent>

      <Suspense fallback={<StepSkeleton />}>
        <StepContent activeIndex={activeStep} index={4}>
          <AnalysisStep />
        </StepContent>
      </Suspense>

      <Suspense fallback={<StepSkeleton />}>
        <StepContent activeIndex={activeStep} index={5}>
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
  );
}
