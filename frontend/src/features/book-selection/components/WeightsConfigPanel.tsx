import { useState } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Play } from 'lucide-react';
import type { CourseLevel, StartSessionRequest, WeightsConfig } from '../types';
import { DEFAULT_WEIGHTS } from '../types';

interface WeightsConfigPanelProps {
  onStart: (request: StartSessionRequest) => void;
  isLoading: boolean;
  disabled?: boolean;
}

const WEIGHT_LABELS: Record<keyof Omit<WeightsConfig, 'W_prac'>, string> = {
  C_topic: 'Topic Relevance',
  C_struc: 'Structure & Pedagogy',
  C_scope: 'Scope & Depth',
  C_pub: 'Publisher Quality',
  C_auth: 'Author Authority',
  C_time: 'Timeliness',
};

export function WeightsConfigPanel({ onStart, isLoading, disabled }: WeightsConfigPanelProps) {
  const [weights, setWeights] = useState<WeightsConfig>({ ...DEFAULT_WEIGHTS });
  const [courseLevel, setCourseLevel] = useState<CourseLevel>('bachelor');

  const coreSum =
    weights.C_topic + weights.C_struc + weights.C_scope +
    weights.C_pub + weights.C_auth + weights.C_time;
  const isValid = Math.abs(coreSum - 1.0) <= 0.001;

  const handleWeightChange = (key: keyof WeightsConfig, value: string) => {
    const num = parseFloat(value);
    if (!isNaN(num) && num >= 0 && num <= 1) {
      setWeights((w) => ({ ...w, [key]: num }));
    }
  };

  const handleStart = () => {
    onStart({ course_level: courseLevel, weights });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Book Selection Configuration</CardTitle>
        <CardDescription>
          Configure scoring weights and course level before starting the AI book discovery.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <Label>Course Level</Label>
          <Select
            value={courseLevel}
            onValueChange={(v) => setCourseLevel(v as CourseLevel)}
          >
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="bachelor">Bachelor</SelectItem>
              <SelectItem value="master">Master</SelectItem>
              <SelectItem value="phd">PhD</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-base">Scoring Weights</Label>
            <span
              className={`text-sm tabular-nums ${
                isValid ? 'text-green-600' : 'text-red-500'
              }`}
            >
              Sum: {coreSum.toFixed(2)} {isValid ? '✓' : '(must = 1.00)'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {(Object.keys(WEIGHT_LABELS) as (keyof typeof WEIGHT_LABELS)[]).map(
              (key) => (
                <div key={key} className="space-y-1">
                  <Label className="text-xs text-muted-foreground">
                    {WEIGHT_LABELS[key]}
                  </Label>
                  <Input
                    type="number"
                    step={0.05}
                    min={0}
                    max={1}
                    value={weights[key]}
                    onChange={(e) => handleWeightChange(key, e.target.value)}
                    className="h-9 tabular-nums"
                  />
                </div>
              ),
            )}
          </div>

          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">
              Practicality Blend (W_prac)
            </Label>
            <Input
              type="number"
              step={0.05}
              min={0}
              max={1}
              value={weights.W_prac}
              onChange={(e) => handleWeightChange('W_prac', e.target.value)}
              className="h-9 w-32 tabular-nums"
            />
            <p className="text-xs text-muted-foreground">
              Blends a practicality score into S_final. 0 = pure academic scoring.
            </p>
          </div>
        </div>

        <Button
          onClick={handleStart}
          disabled={disabled || isLoading || !isValid}
          className="w-full"
        >
          {isLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Start Book Discovery
        </Button>
      </CardContent>
    </Card>
  );
}
