import {
  AlertTriangle,
  BookOpen,
  CircleHelp,
  Clock3,
  ExternalLink,
  PlayCircle,
  RefreshCw,
} from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import {
  getIndividualLearningPath,
  type IndividualLearningPathResponse,
} from '@/features/individual-learning/api';

function getErrorStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

function ResourceLinks({
  items,
  icon: Icon,
  emptyLabel,
}: {
  items: Array<{ id: string; title: string; url: string; domain?: string | null }>;
  icon: typeof BookOpen;
  emptyLabel: string;
}) {
  if (items.length === 0) {
    return <span className="text-sm text-muted-foreground">{emptyLabel}</span>;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <a
          key={item.id}
          href={item.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm hover:bg-accent"
        >
          <span className="flex min-w-0 items-center gap-2">
            <Icon className="size-4 shrink-0" />
            <span className="truncate">{item.title}</span>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
            {item.domain ?? 'link'}
            <ExternalLink className="size-4" />
          </span>
        </a>
      ))}
    </div>
  );
}

export default function IndividualLearningPathPage() {
  const [path, setPath] = useState<IndividualLearningPathResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadPath() {
      try {
        const data = await getIndividualLearningPath();
        if (active) {
          setPath(data);
          setError(null);
        }
      } catch (error) {
        if (active) {
          setPath(null);
          if (getErrorStatus(error) !== 404) {
            setError('We could not load your individual learning path.');
          }
        }
        if (getErrorStatus(error) !== 404) {
          console.error(error);
          toast.error('Failed to load your individual learning path.');
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    loadPath();

    return () => {
      active = false;
    };
  }, [loadAttempt]);

  const retryLearningPath = () => {
    setError(null);
    setIsLoading(true);
    setLoadAttempt((attempt) => attempt + 1);
  };

  return (
    <main className="mx-auto flex w-full max-w-6xl flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">Learning path</h1>
        <p className="text-sm text-muted-foreground">
          Review the selected skills and the attached readings, videos, and questions.
        </p>
      </div>

      {!isLoading && path && (path.build_status === 'partial' || path.build_status === 'failed') ? (
        <Alert variant={path.build_status === 'failed' ? 'destructive' : 'default'}>
          <AlertTriangle className="size-4" />
          <AlertTitle>
            {path.build_status === 'failed'
              ? 'Learning path build failed'
              : 'Learning path partially built'}
          </AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>
              {path.build_error ??
                (path.build_status === 'failed'
                  ? 'No learning resources were generated.'
                  : 'Some selected skills do not have resources yet.')}
            </span>
            {path.build_run_id ? <Badge variant="outline">Run {path.build_run_id}</Badge> : null}
            <Button type="button" size="sm" variant="outline" asChild>
              <Link to="/individual/skills">Return to skill selection</Link>
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      {isLoading ? (
        <div className="rounded-md border p-8 text-sm text-muted-foreground">Loading learning path...</div>
      ) : error ? (
        <Alert variant="destructive">
          <BookOpen className="size-4" />
          <AlertTitle>Learning path unavailable</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            <span>{error}</span>
            <Button type="button" size="sm" variant="outline" onClick={retryLearningPath}>
              <RefreshCw className="size-4" />
              Retry learning path
            </Button>
          </AlertDescription>
        </Alert>
      ) : !path || path.selected_skills.length === 0 ? (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BookOpen className="size-5" />
            </EmptyMedia>
            <EmptyTitle>No learning path yet</EmptyTitle>
            <EmptyDescription>
              Build the path from the skill-selection screen after choosing market skills.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader>
                <CardTitle>Total selected skills</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{path.total_selected_skills}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Skills with resources</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{path.skills_with_resources}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>User ID</CardTitle>
              </CardHeader>
              <CardContent className="text-2xl font-semibold">{path.user_id}</CardContent>
            </Card>
          </div>

          <div className="grid gap-4">
            {path.selected_skills.map((skill) => {
              const isPending =
                skill.readings.length === 0 &&
                skill.videos.length === 0 &&
                skill.questions.length === 0;

              return (
                <Card key={skill.name}>
                  <CardHeader>
                    <div className="flex flex-wrap items-center gap-2">
                      <CardTitle>{skill.name}</CardTitle>
                      {skill.source ? <Badge variant="outline">{skill.source}</Badge> : null}
                    </div>
                    <CardDescription>
                      {skill.description ?? 'No description was returned for this skill.'}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-6">
                    {isPending ? (
                      <div className="flex items-start gap-3 rounded-md border p-4 text-sm text-muted-foreground">
                        <Clock3 className="mt-0.5 size-4 shrink-0" />
                        <span>Content is still being assembled for this skill.</span>
                      </div>
                    ) : null}

                    <div className="grid gap-6 lg:grid-cols-3">
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          <BookOpen className="size-4" />
                          Readings
                        </div>
                        <ResourceLinks
                          items={skill.readings}
                          icon={BookOpen}
                          emptyLabel="No readings yet."
                        />
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          <PlayCircle className="size-4" />
                          Videos
                        </div>
                        <ResourceLinks
                          items={skill.videos}
                          icon={PlayCircle}
                          emptyLabel="No videos yet."
                        />
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center gap-2 text-sm font-medium">
                          <CircleHelp className="size-4" />
                          Questions
                        </div>
                        <div className="space-y-2">
                          {skill.questions.length > 0 ? (
                            skill.questions.map((question) => (
                              <div key={question.id} className="rounded-md border p-3">
                                <div className="flex items-center justify-between gap-2">
                                  <span className="text-sm font-medium">{question.text}</span>
                                  <Badge variant="secondary" className="capitalize">
                                    {question.difficulty}
                                  </Badge>
                                </div>
                                <div className="mt-2 text-sm text-muted-foreground">
                                  {question.options.length} option(s)
                                </div>
                              </div>
                            ))
                          ) : (
                            <span className="text-sm text-muted-foreground">No questions yet.</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </main>
  );
}
