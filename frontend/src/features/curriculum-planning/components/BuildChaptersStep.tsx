import { useState, useEffect } from 'react';
import { Sparkles, Loader2, AlertCircle, ArrowRight } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useCourseDetail } from '@/features/courses/context/CourseDetailContext';
import { generateChapterPlan, getChapterPlan } from '../api';
import { ChapterPlanBuilder } from './ChapterPlanBuilder';
import type { ChapterPlanResponse } from '../types';

export function BuildChaptersStep() {
  const { courseId, course, goToNext, setHasChapters } = useCourseDetail();
  const [plan, setPlan] = useState<ChapterPlanResponse | null>(null);
  const [generating, setGenerating] = useState(false);
  const [planLoading, setPlanLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const disabled = course?.extraction_status !== 'finished';

  useEffect(() => {
    if (disabled) return;
    setPlanLoading(true);
    getChapterPlan(courseId)
      .then((p) => {
        if (p.chapters.length > 0) {
          setPlan(p);
          setHasChapters(true);
        }
      })
      .catch(() => {
        // no plan yet, that's fine
      })
      .finally(() => setPlanLoading(false));
  }, [courseId, disabled, setHasChapters]);

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const p = await generateChapterPlan(courseId);
      setPlan(p);
      if (p.chapters.length > 0) {
        setHasChapters(true);
      }
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
            Organize your uploaded documents into curriculum chapters.
          </p>
        </div>
        <Button
          onClick={() => void handleGenerate()}
          disabled={disabled || generating}
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

      {!planLoading && plan && plan.chapters.length > 0 && (
        <ChapterPlanBuilder initialPlan={plan} onSave={setPlan} courseId={courseId} />
      )}

      {plan && plan.chapters.length > 0 && (
        <div className="flex justify-end pt-2">
          <Button onClick={goToNext} variant="outline" className="gap-2">
            Continue to Select Books
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
