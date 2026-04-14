import { useEffect, useMemo, useState, useTransition } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle2, Loader2, ShieldAlert, Sparkles } from 'lucide-react';
import { useForm, type Control } from 'react-hook-form';
import { z } from 'zod';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Form, FormControl, FormField, FormItem, FormMessage } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
  getChapterQuiz,
  submitChapterQuiz,
  type ChapterQuizResponse,
  type QuizAnswerResult,
  type QuizSubmitResponse,
  type QuizAnswerSubmission,
} from '../api';

const ANSWER_OPTIONS = ['A', 'B', 'C', 'D'] as const;
type QuizChoice = (typeof ANSWER_OPTIONS)[number];
type QuizFormValues = { answers: Record<string, QuizChoice> };

function isQuizChoice(value: unknown): value is QuizChoice {
  return typeof value === 'string' && ANSWER_OPTIONS.includes(value as QuizChoice);
}

function getErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

function getErrorDetail(error: unknown): string | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === 'string' ? detail : null;
}

function buildAnswerSchema(questions: ChapterQuizResponse['questions']) {
  return z
    .object({
      answers: z.record(z.string(), z.enum(ANSWER_OPTIONS)),
    })
    .superRefine((value, ctx) => {
      for (const question of questions) {
        if (value.answers[question.id]) {
          continue;
        }
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Select an answer before submitting.',
          path: ['answers', question.id],
        });
      }
    });
}

function getDefaultAnswers(quiz: ChapterQuizResponse) {
  return Object.fromEntries(
    Object.entries(quiz.previous_answers).map(([questionId, answer]) => [
      questionId,
      answer.selected_option,
    ]),
  ) as Record<string, QuizChoice>;
}

function formatResultBadge(result: QuizAnswerResult) {
  return result.answered_right ? 'Correct' : 'Incorrect';
}

export default function ChapterQuizPage() {
  const { id: courseIdParam, chapterIndex: chapterIndexParam } = useParams<{
    id: string;
    chapterIndex: string;
  }>();
  const navigate = useNavigate();

  const courseId = Number(courseIdParam);
  const chapterIndex = Number(chapterIndexParam);

  const [quiz, setQuiz] = useState<ChapterQuizResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadQuiz() {
      if (!Number.isFinite(courseId) || !Number.isFinite(chapterIndex)) {
        setLoadError('This quiz link is invalid.');
        setLoading(false);
        return;
      }

      setLoading(true);
      setLoadError(null);

      try {
        const data = await getChapterQuiz(courseId, chapterIndex);
        if (!active) {
          return;
        }
        setQuiz(data);
      } catch (error) {
        if (!active) {
          return;
        }

        if (getErrorStatus(error) === 403) {
          toast.error('Join the course before opening the quiz.');
          navigate(`/courses/${courseId}`, { replace: true });
          return;
        }

        const detail = getErrorDetail(error);
        setLoadError(
          detail ??
            (getErrorStatus(error) === 404
              ? 'This chapter does not have a diagnostic quiz yet.'
              : getErrorStatus(error) === 400
                ? 'This chapter is still locked.'
                : 'Failed to load the chapter quiz.'),
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void loadQuiz();

    return () => {
      active = false;
    };
  }, [chapterIndex, courseId, navigate]);

  if (loading) {
    return (
      <div className="flex min-h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!quiz || loadError) {
    return (
      <div className="flex min-h-full items-center justify-center p-6">
        <Card className="w-full max-w-2xl border-border/60">
          <CardContent className="flex flex-col items-center gap-4 pt-6 text-center">
            <ShieldAlert className="h-10 w-10 text-muted-foreground/70" />
            <div className="space-y-1">
              <CardTitle className="text-xl">Quiz unavailable</CardTitle>
              <CardDescription>{loadError ?? 'This chapter quiz could not be loaded.'}</CardDescription>
            </div>
            <Button asChild variant="outline">
              <Link to={`/courses/${courseId}/learning-path`}>Back to learning path</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <ChapterQuizForm quiz={quiz} courseId={courseId} chapterIndex={chapterIndex} />;
}

function ChapterQuizForm({
  quiz,
  courseId,
  chapterIndex,
}: {
  quiz: ChapterQuizResponse;
  courseId: number;
  chapterIndex: number;
}) {
  const navigate = useNavigate();
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [submission, setSubmission] = useState<QuizSubmitResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPending, startTransition] = useTransition();

  const schema = useMemo(() => buildAnswerSchema(quiz.questions), [quiz.questions]);
  const defaultAnswers = useMemo(() => getDefaultAnswers(quiz), [quiz]);

  const form = useForm<QuizFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { answers: defaultAnswers },
  });

  const answers = form.watch('answers') ?? {};
  const answeredCount = quiz.questions.reduce(
    (count, question) => count + (isQuizChoice(answers[question.id]) ? 1 : 0),
    0,
  );
  const allAnswered = quiz.questions.length > 0 && answeredCount === quiz.questions.length;
  const hasRetakeAnswers = Object.keys(quiz.previous_answers).length > 0;

  const onSubmit = form.handleSubmit((values) => {
    const payload: QuizAnswerSubmission[] = quiz.questions.map((question) => ({
      question_id: question.id,
      selected_option: values.answers[question.id]!,
    }));

    setIsSubmitting(true);
    startTransition(() => {
      void (async () => {
        try {
          const result = await submitChapterQuiz(courseId, chapterIndex, payload);
          setSubmission(result);
          setSummaryOpen(true);
        } catch (error) {
          const detail = getErrorDetail(error);
          toast.error(detail ?? 'Failed to submit chapter quiz.');
        } finally {
          setIsSubmitting(false);
        }
      })();
    });
  });

  return (
    <div className="flex min-h-full flex-col gap-6 overflow-auto p-6">
      <section className="rounded-3xl border border-border/60 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.14),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.14),transparent_32%)] p-6 shadow-sm">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="space-y-2">
            <Badge variant="outline" className="rounded-full border-white/20 bg-background/70 px-3 py-1 text-[11px]">
              Diagnostic quiz
            </Badge>
            <div className="space-y-1">
              <h1 className="text-3xl font-semibold tracking-tight">{quiz.chapter_title}</h1>
              <p className="max-w-2xl text-sm text-muted-foreground">
                Diagnostic quiz - one question per selected skill.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant="outline" className="rounded-full bg-background/70 px-3 py-1">
              {answeredCount}/{quiz.questions.length} answered
            </Badge>
            <Badge variant="secondary" className="rounded-full px-3 py-1">
              Chapter {quiz.chapter_index}
            </Badge>
          </div>
        </div>
      </section>

      {hasRetakeAnswers && (
        <Card className="border-amber-200/70 bg-amber-50/90 text-amber-950 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
          <CardContent className="flex items-start gap-3 pt-6">
            <Sparkles className="mt-0.5 h-5 w-5 shrink-0" />
            <div className="space-y-1">
              <p className="font-medium">Retake available</p>
              <p className="text-sm">
                Previous answers are pre-filled. Submitting again overwrites the saved attempt.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {quiz.questions.length === 0 ? (
        <Card className="border-border/60">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">This chapter does not have any quiz questions yet.</p>
          </CardContent>
        </Card>
      ) : (
        <Form {...form}>
          <form onSubmit={onSubmit} className="flex flex-1 flex-col gap-4">
            <div className="space-y-4">
              {quiz.questions.map((question, index) => (
                <QuestionPrompt
                  key={question.id}
                  question={question}
                  index={index + 1}
                  control={form.control}
                />
              ))}
            </div>

            <div className="sticky bottom-0 mt-auto border-t border-border/60 bg-background/95 p-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">
                  Answer every question to unlock the next step.
                </p>
                <div className="flex items-center gap-2">
                  <Button asChild variant="outline">
                    <Link to={`/courses/${courseId}/learning-path`}>Back to learning path</Link>
                  </Button>
                  <Button type="submit" disabled={!allAnswered || isSubmitting || isPending} className="gap-2">
                    {isSubmitting || isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                    Submit quiz
                  </Button>
                </div>
              </div>
            </div>
          </form>
        </Form>
      )}

      <Dialog open={summaryOpen} onOpenChange={setSummaryOpen}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              Quiz submitted
            </DialogTitle>
            <DialogDescription>
              {submission
                ? `${submission.skills_known.length} skill${
                    submission.skills_known.length === 1 ? '' : 's'
                  } are already known.`
                : 'Your chapter diagnostic has been recorded.'}
            </DialogDescription>
          </DialogHeader>

          {submission && (
            <div className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Card className="border-border/60">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Known skills</CardTitle>
                    <CardDescription>Skills answered correctly on this attempt.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {submission.skills_known.length > 0 ? (
                      submission.skills_known.map((skill) => (
                        <Badge key={skill} variant="secondary" className="mr-2">
                          {skill}
                        </Badge>
                      ))
                    ) : (
                      <p className="text-sm text-muted-foreground">None yet.</p>
                    )}
                  </CardContent>
                </Card>

                <Card className="border-border/60">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-base">Results</CardTitle>
                    <CardDescription>Correct and incorrect answers for each skill.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <p className="text-sm text-muted-foreground">
                      {submission.results.length} question{submission.results.length === 1 ? '' : 's'} checked.
                    </p>
                  </CardContent>
                </Card>
              </div>

              <div className="max-h-[45vh] space-y-2 overflow-y-auto pr-1">
                {submission.results.map((result) => (
                  <div
                    key={result.question_id}
                    className={cn(
                      'flex items-start justify-between gap-3 rounded-xl border p-4',
                      result.answered_right
                        ? 'border-emerald-200 bg-emerald-50/80 dark:border-emerald-500/20 dark:bg-emerald-500/10'
                        : 'border-rose-200 bg-rose-50/80 dark:border-rose-500/20 dark:bg-rose-500/10',
                    )}
                  >
                    <div className="space-y-1">
                      <p className="font-medium">{result.skill_name}</p>
                      <p className="text-sm text-muted-foreground">
                        Selected {result.selected_option}, correct answer {result.correct_option}
                      </p>
                    </div>
                    <Badge variant={result.answered_right ? 'default' : 'destructive'}>
                      {formatResultBadge(result)}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" onClick={() => navigate(`/courses/${courseId}/learning-path`)}>
              Continue to learning
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function QuestionPrompt({
  question,
  index,
  control,
}: {
  question: ChapterQuizResponse['questions'][number];
  index: number;
  control: Control<QuizFormValues>;
}) {
  return (
    <FormField
      control={control}
      name={`answers.${question.id}`}
      render={({ field }) => (
        <FormItem>
          <Card className="border-border/60 shadow-none">
            <CardHeader className="space-y-2 border-b border-border/60 pb-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <CardTitle className="text-base">
                  Question {index}
                </CardTitle>
                <Badge variant="outline" className="rounded-full">
                  {question.skill_name}
                </Badge>
              </div>
              <CardDescription className="text-sm text-foreground">{question.text}</CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              <FormControl>
                <RadioGroup
                  value={field.value ?? ''}
                  onValueChange={field.onChange}
                  className="gap-3"
                >
                  {question.options.map((option, optionIndex) => {
                    const optionValue = ANSWER_OPTIONS[optionIndex];
                    const optionId = `${question.id}-${optionValue}`;

                    return (
                      <div
                        key={optionValue}
                        className={cn(
                          'flex items-start gap-3 rounded-xl border p-3 transition-colors',
                          field.value === optionValue
                            ? 'border-primary/40 bg-primary/5'
                            : 'border-border/60 bg-background hover:bg-accent/50',
                        )}
                      >
                        <RadioGroupItem id={optionId} value={optionValue} className="mt-0.5" />
                        <div className="grid gap-1">
                          <Label htmlFor={optionId} className="cursor-pointer text-sm font-medium">
                            {optionValue}. {option}
                          </Label>
                        </div>
                      </div>
                    );
                  })}
                </RadioGroup>
              </FormControl>
              <FormMessage className="mt-3" />
            </CardContent>
          </Card>
        </FormItem>
      )}
    />
  );
}
