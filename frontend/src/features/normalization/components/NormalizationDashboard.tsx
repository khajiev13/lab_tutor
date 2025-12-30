import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Play, Square, Wand2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

import { listCourseConcepts } from '@/features/normalization/api';
import {
  startNormalizationStream,
} from '@/services/normalization';
import type { NormalizationStreamEvent } from '@/services/normalization';

type Props = {
  courseId: number;
  disabled?: boolean;
};

export function NormalizationDashboard({ courseId, disabled }: Props) {
  const navigate = useNavigate();
  const [concepts, setConcepts] = useState<string[]>([]);
  const [isLoadingConcepts, setIsLoadingConcepts] = useState(false);

  const [isRunning, setIsRunning] = useState(false);
  const [lastEvent, setLastEvent] = useState<NormalizationStreamEvent | null>(null);
  const [reviewId, setReviewId] = useState<string | null>(null);
  const [needsReview, setNeedsReview] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const refreshConcepts = useCallback(async () => {
    setIsLoadingConcepts(true);
    try {
      const data = await listCourseConcepts(courseId);
      setConcepts(data);
    } catch (e) {
      toast.error('Failed to load concepts');
      console.error(e);
    } finally {
      setIsLoadingConcepts(false);
    }
  }, [courseId]);

  useEffect(() => {
    void refreshConcepts();
  }, [refreshConcepts]);

  const handleStart = useCallback(async () => {
    if (disabled) return;
    if (isRunning) return;

    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    setIsRunning(true);
    setLastEvent(null);
    setNeedsReview(false);
    setReviewId(null);

    try {
      await startNormalizationStream({
        courseId,
        signal: abort.signal,
        onEvent: (evt) => {
          setLastEvent(evt);

          if (evt.type === 'complete') {
            toast.success('Normalization run completed');
            if (evt.requires_review && evt.review_id) {
              setNeedsReview(true);
              setReviewId(evt.review_id);
              toast.message('Agent needs your feedback to merge concepts');
            }
            setIsRunning(false);
          }
          if (evt.type === 'error') {
            toast.error('Normalization failed');
            setIsRunning(false);
          }
        },
        onError: (err) => {
          console.error(err);
        },
      });
    } catch (e) {
      const isAbort =
        typeof e === 'object' &&
        e !== null &&
        'name' in e &&
        typeof (e as Record<string, unknown>).name === 'string' &&
        (e as Record<string, unknown>).name === 'AbortError';
      if (!isAbort) {
        toast.error('Failed to start normalization stream');
        console.error(e);
      }
    } finally {
      setIsRunning(false);
    }
  }, [courseId, disabled, isRunning]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setIsRunning(false);
  }, []);

  const activity = lastEvent?.agent_activity ?? (isRunning ? 'Working…' : '—');

  return (
    <div className="space-y-6">
      {needsReview && reviewId && (
        <Alert className="border-primary/30 bg-primary/5">
          <Wand2 className="h-4 w-4" />
          <AlertTitle>Agent needs your feedback</AlertTitle>
          <AlertDescription className="flex items-center justify-between gap-3">
            <span>
              Review the suggested merges, approve/reject them, then apply approved merges to your
              knowledge graph.
            </span>
            <Button 
              onClick={() => navigate(`/courses/${courseId}/reviews/${reviewId}`)} 
              disabled={disabled}
            >
              Review merges
            </Button>
          </AlertDescription>
        </Alert>
      )}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <div className="space-y-1">
            <CardTitle className="text-lg">Concept normalization</CardTitle>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {isLoadingConcepts ? (
                <span className="inline-flex items-center gap-2">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Loading concepts…
                </span>
              ) : (
                <span>{concepts.length} concepts</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => void refreshConcepts()}
              disabled={disabled || isLoadingConcepts || isRunning}
            >
              Refresh
            </Button>
            {isRunning ? (
              <Button variant="destructive" onClick={handleStop}>
                <Square className="mr-2 h-4 w-4" />
                Stop
              </Button>
            ) : (
              <Button onClick={() => void handleStart()} disabled={disabled || concepts.length === 0}>
                {isRunning ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Play className="mr-2 h-4 w-4" />
                )}
                Start
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Separator />
          <div className="flex items-center gap-3">
            {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            <div className="text-sm text-muted-foreground">
              {isRunning ? 'Agent is working… please wait.' : 'Ready.'}{' '}
              <span className="text-muted-foreground/70">{activity}</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}


