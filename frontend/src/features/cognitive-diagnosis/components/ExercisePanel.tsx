import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Loader2, Lightbulb, CheckCircle, XCircle, HelpCircle } from 'lucide-react';
import type { ExerciseResponse } from '../api';
import { diagnosisApi } from '../api';

interface ExercisePanelProps {
  skillName: string;
  courseId: number;
  onAnswer?: (isCorrect: boolean) => void;
}

export function ExercisePanel({ skillName, courseId, onAnswer }: ExercisePanelProps) {
  const [exercise, setExercise] = useState<ExerciseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [selectedOption, setSelectedOption] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [showHint, setShowHint] = useState(false);
  const [hintIdx, setHintIdx] = useState(0);
  const [startTime] = useState(Date.now());

  const loadExercise = async () => {
    setLoading(true);
    setSelectedOption(null);
    setSubmitted(false);
    setShowHint(false);
    setHintIdx(0);
    try {
      const resp = await diagnosisApi.getExercise(skillName);
      setExercise(resp.data);
    } catch (err) {
      console.error('Failed to load exercise', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!exercise || !selectedOption) return;
    setSubmitted(true);
    const isCorrect = selectedOption === exercise.correct_answer;
    const timeSpent = Math.round((Date.now() - startTime) / 1000);

    try {
      await diagnosisApi.logInteraction({
        question_id: exercise.exercise_id,
        is_correct: isCorrect,
        time_spent_sec: timeSpent,
        course_id: courseId,
      });
    } catch {
      // non-fatal
    }

    onAnswer?.(isCorrect);
  };

  if (!exercise && !loading) {
    return (
      <div className="text-center py-6">
        <p className="text-sm text-muted-foreground mb-3">
          Ready to practice <strong>{skillName}</strong>?
        </p>
        <Button onClick={loadExercise}>Generate Exercise</Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground mr-2" />
        <span className="text-sm text-muted-foreground">Generating adaptive exercise…</span>
      </div>
    );
  }

  if (!exercise) return null;

  const isCorrect = submitted && selectedOption === exercise.correct_answer;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <CardTitle className="text-sm font-semibold">{exercise.skill_name}</CardTitle>
            <CardDescription className="text-xs">
              {exercise.difficulty_band} · {exercise.estimated_time_seconds}s · {exercise.why}
            </CardDescription>
          </div>
          {exercise.quality_warning && (
            <Badge variant="outline" className="text-xs text-orange-600">Review manually</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm leading-relaxed">{exercise.problem}</p>

        {/* Multiple choice */}
        {exercise.format === 'multiple_choice' && exercise.options.length > 0 && (
          <div className="space-y-2">
            {exercise.options.map((opt, i) => {
              const isSelected = selectedOption === opt;
              const isAnswer = submitted && opt === exercise.correct_answer;
              const isWrong = submitted && isSelected && !isAnswer;
              return (
                <button
                  key={i}
                  disabled={submitted}
                  onClick={() => setSelectedOption(opt)}
                  className={`w-full text-left p-3 rounded-lg border text-sm transition-colors ${
                    isAnswer
                      ? 'border-green-500 bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200'
                      : isWrong
                      ? 'border-red-400 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200'
                      : isSelected
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:border-primary/50 hover:bg-muted/50'
                  }`}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-xs opacity-50">{String.fromCharCode(65 + i)}.</span>
                    <span>{opt}</span>
                    {isAnswer && <CheckCircle className="h-4 w-4 ml-auto text-green-600" />}
                    {isWrong && <XCircle className="h-4 w-4 ml-auto text-red-500" />}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {/* Open-ended */}
        {exercise.format !== 'multiple_choice' && !submitted && (
          <textarea
            className="w-full border rounded-lg p-3 text-sm resize-none min-h-[80px] bg-background"
            placeholder="Type your answer here…"
            onChange={(e) => setSelectedOption(e.target.value)}
          />
        )}

        {/* Hints */}
        {exercise.hints.length > 0 && !submitted && (
          <div>
            {!showHint ? (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs"
                onClick={() => setShowHint(true)}
              >
                <HelpCircle className="h-3 w-3 mr-1" />
                Show hint
              </Button>
            ) : (
              <div className="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                <Lightbulb className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    {exercise.hints[hintIdx]}
                  </p>
                  {hintIdx < exercise.hints.length - 1 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-xs h-6 text-amber-700 dark:text-amber-300"
                      onClick={() => setHintIdx(hintIdx + 1)}
                    >
                      Next hint
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Submit / result */}
        {!submitted ? (
          <Button
            className="w-full"
            disabled={!selectedOption}
            onClick={handleSubmit}
          >
            Submit Answer
          </Button>
        ) : (
          <div className="space-y-3">
            <div className={`p-3 rounded-lg text-sm ${
              isCorrect
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            }`}>
              <div className="flex items-center gap-2 font-medium">
                {isCorrect ? (
                  <><CheckCircle className="h-4 w-4 text-green-600" /> <span className="text-green-800 dark:text-green-200">Correct!</span></>
                ) : (
                  <><XCircle className="h-4 w-4 text-red-500" /> <span className="text-red-800 dark:text-red-200">Not quite.</span></>
                )}
              </div>
              {!isCorrect && (
                <p className="text-xs mt-1 text-muted-foreground">
                  Correct answer: <strong>{exercise.correct_answer}</strong>
                </p>
              )}
            </div>
            <Button variant="outline" className="w-full" onClick={loadExercise}>
              Next Exercise
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
