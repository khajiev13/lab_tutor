import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, TriangleAlert } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getLearningPath, type LearningPathResponse } from '../api';
import { ResourceAgentPane } from '../components/ResourceAgentPane';
import { ResourceViewerPane } from '../components/ResourceViewerPane';
import {
  findAccessibleLearningPathResource,
  isStudyResourceKind,
} from '../resource-utils';

type StudyLocationState = {
  fromLearningPath?: boolean;
};

function getErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

function hasHistoryBackEntry(locationState: StudyLocationState | null): boolean {
  if (locationState?.fromLearningPath) {
    return true;
  }

  if (typeof window === 'undefined') {
    return false;
  }

  const historyState = window.history.state as { idx?: number } | null;
  if (typeof historyState?.idx === 'number') {
    return historyState.idx > 0;
  }

  return window.history.length > 1;
}

export default function StudentLearningPathStudyPage() {
  const { id: courseId, resourceKind, resourceId } = useParams<{
    id: string;
    resourceKind: string;
    resourceId: string;
  }>();
  const navigate = useNavigate();
  const location = useLocation();
  const numericCourseId = Number(courseId);
  const learningPathHref = courseId ? `/courses/${courseId}/learning-path` : '/courses';
  const [learningPath, setLearningPath] = useState<LearningPathResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    if (!Number.isFinite(numericCourseId) || !isStudyResourceKind(resourceKind) || !resourceId) {
      setLearningPath(null);
      setLoadFailed(false);
      setIsLoading(false);
      return;
    }

    let cancelled = false;

    async function loadStudyPath() {
      setIsLoading(true);
      setLoadFailed(false);

      try {
        const data = await getLearningPath(numericCourseId);
        if (!cancelled) {
          setLearningPath(data);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }

        if (getErrorStatus(error) === 403) {
          toast.error('Join the course before opening the learning path.');
          navigate(`/courses/${numericCourseId}`, { replace: true });
          return;
        }

        if (getErrorStatus(error) === 404) {
          setLearningPath(null);
          return;
        }

        setLearningPath(null);
        setLoadFailed(true);
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadStudyPath();

    return () => {
      cancelled = true;
    };
  }, [navigate, numericCourseId, resourceId, resourceKind]);

  const resolvedResource = useMemo(() => {
    if (!learningPath || !isStudyResourceKind(resourceKind)) {
      return null;
    }

    return findAccessibleLearningPathResource(learningPath, resourceKind, resourceId);
  }, [learningPath, resourceId, resourceKind]);

  const handleClose = useCallback(() => {
    if (hasHistoryBackEntry((location.state as StudyLocationState | null) ?? null)) {
      navigate(-1);
      return;
    }

    navigate(learningPathHref, { replace: true });
  }, [learningPathHref, location.state, navigate]);

  const fallbackContent = useMemo(() => {
    if (!Number.isFinite(numericCourseId) || !isStudyResourceKind(resourceKind) || !resourceId) {
      return {
        title: 'Invalid study link',
        description: 'This study route is missing a valid resource type or resource id.',
      };
    }

    if (loadFailed) {
      return {
        title: 'Study resource unavailable',
        description: 'We could not load your learning path right now. Return to the learning path and try again.',
      };
    }

    return {
      title: 'Resource not available for study',
      description:
        'This resource is missing, filtered out, or not part of your currently accessible learning path.',
    };
  }, [loadFailed, numericCourseId, resourceId, resourceKind]);

  return (
    <div
      data-testid="study-page-shell"
      className="flex h-svh min-h-svh flex-col overflow-hidden bg-background p-3 md:p-4"
    >
      {isLoading ? (
        <StudyPageSkeleton />
      ) : resolvedResource ? (
        <div
          data-testid="study-page-layout"
          className="grid min-h-0 flex-1 gap-3 md:gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]"
        >
          <ResourceViewerPane courseId={numericCourseId} resource={resolvedResource} onClose={handleClose} />
          <ResourceAgentPane resource={resolvedResource} />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <StudyResourceUnavailableCard
            title={fallbackContent.title}
            description={fallbackContent.description}
            returnHref={learningPathHref}
          />
        </div>
      )}
    </div>
  );
}

function StudyPageSkeleton() {
  return (
    <div
      data-testid="study-page-layout"
      className="grid min-h-0 flex-1 gap-3 md:gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]"
    >
      <Card className="flex h-full min-h-0 flex-col overflow-hidden border-border/60 shadow-none">
        <div className="space-y-4 border-b border-border/60 px-5 py-4">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-4 w-40" />
        </div>
        <div className="min-h-0 flex-1 space-y-4 p-5">
          <Skeleton className="h-7 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-10/12" />
          <Skeleton className="h-4 w-full" />
        </div>
      </Card>

      <Card className="hidden h-full min-h-0 border-border/60 shadow-none md:flex md:flex-col">
        <CardHeader>
          <Skeleton className="h-6 w-36" />
        </CardHeader>
        <CardContent className="min-h-0 flex-1 space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
        </CardContent>
      </Card>
    </div>
  );
}

function StudyResourceUnavailableCard({
  title,
  description,
  returnHref,
}: {
  title: string;
  description: string;
  returnHref: string;
}) {
  return (
    <Card className="mx-auto w-full max-w-2xl border-border/60 shadow-none">
      <CardHeader className="space-y-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
          <TriangleAlert className="h-5 w-5" />
        </div>
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <Button asChild className="gap-2">
          <Link to={returnHref}>
            <ArrowLeft className="h-4 w-4" />
            Return to learning path
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}
