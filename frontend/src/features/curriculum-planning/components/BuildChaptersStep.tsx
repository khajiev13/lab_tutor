import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Sparkles, Loader2, AlertCircle, ArrowRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useCourseDetail } from '@/features/courses/context/CourseDetailContext';
import { generateChapterPlan, getChapterPlan } from '@/features/curriculum-planning/api';
import { ChapterPlanBuilder } from '@/features/curriculum-planning/components/ChapterPlanBuilder';
import type { ChapterPlanResponse } from '@/features/curriculum-planning/types';

export function BuildChaptersStep() {
  const { courseId, materialsReady, goToNext, setHasChapters, refreshChapterPlan } = useCourseDetail();
  const [plan, setPlan] = useState<ChapterPlanResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loadError, setLoadError] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  const disabled = !materialsReady;

  useEffect(() => {
    if (disabled) return;
    let cancelled = false;
    setPlanLoading(true);
    setLoadError(false);
    getChapterPlan(courseId)
      .then((p) => {
        if (cancelled) return;
        setPlan(p.chapters.length > 0 ? p : null);
        setHasChapters(p.chapters.length > 0);
      })
      .catch(() => { if (!cancelled) setLoadError(true); })
      .finally(() => { if (!cancelled) setPlanLoading(false); });
    return () => { cancelled = true; };
  }, [courseId, disabled, setHasChapters, loadAttempt]);

  const acceptPlan = (saved: ChapterPlanResponse) => {
    setPlan(saved);
    setHasChapters(saved.chapters.length > 0);
    refreshChapterPlan();
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const p = await generateChapterPlan(courseId);
      acceptPlan(p);
    } catch {
      setError('Failed to generate chapter plan. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-4">
      {disabled && (
        <Alert className="bg-muted/50">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Extraction required</AlertTitle>
          <AlertDescription>
            Run extraction first to populate teacher documents.
          </AlertDescription>
        </Alert>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-medium">Chapter Plan</h3>
          <p className="text-sm text-muted-foreground">
            Organize your uploaded documents into curriculum chapters so extracted skills can be linked to your course.
          </p>
        </div>
        <Button
          onClick={() => void handleGenerate()}
          disabled={disabled || generating || planLoading || loadError}
          variant={plan ? 'outline' : 'default'}
        >
          {generating ? (
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
          ) : (
            <Sparkles className="h-4 w-4 mr-2" />
          )}
          {plan ? 'Regenerate' : 'Generate Plan'}
        </Button>
      </div>

      {loadError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Could not load your chapter plan. Retry before generating a new one.
            <Button className="mt-2" variant="outline" size="sm" onClick={() => { setLoadAttempt((value) => value + 1); refreshChapterPlan(); }}>Retry loading plan</Button>
          </AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {planLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading existing plan...
        </div>
      )}

      {!planLoading && !loadError && plan && plan.chapters.length > 0 && (
        <ChapterPlanBuilder initialPlan={plan} onSave={acceptPlan} courseId={courseId} />
      )}

      {!planLoading && !loadError && plan && plan.chapters.length > 0 && (
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <Button asChild className="gap-2">
            <Link to={`/courses/${courseId}/market-analyst`}>Return to Swarm<ArrowRight className="h-4 w-4" /></Link>
          </Button>
          <Button onClick={goToNext} variant="outline" className="gap-2">
            Continue to Select Books
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
