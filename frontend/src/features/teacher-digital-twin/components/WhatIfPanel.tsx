/** What-If Simulation panel — Feature 5 */
import { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Loader2, Sparkles, PlayCircle, Plus, X } from 'lucide-react';
import { toast } from 'sonner';
import { teacherTwinApi } from '../api';
import type { WhatIfResponse, WhatIfSkillInput } from '../api';

function SimulationResults({ data }: { data: WhatIfResponse }) {
  const totalClassGain = useMemo(
    () => data.skill_impacts.reduce((acc, item) => acc + item.class_gain, 0),
    [data.skill_impacts]
  );
  return (
    <div className="space-y-4 mt-4">
      {/* Summary */}
      <div className="p-3 bg-muted/50 rounded-lg flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">Total Class Gain</p>
          <p className="text-2xl font-bold tabular-nums text-green-600">
            +{(totalClassGain * 100).toFixed(1)}%
          </p>
        </div>
        <Badge variant={data.mode === 'automatic' ? 'default' : 'outline'} className="capitalize">
          {data.mode} mode
        </Badge>
      </div>

      {/* Recommendation */}
      {data.summary && (
        <div className="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg">
          <p className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1">Recommendation</p>
          <p className="text-sm text-blue-900 dark:text-blue-200">{data.summary}</p>
          {data.llm_recommendation && (
            <p className="text-xs text-blue-900/80 dark:text-blue-200/90 mt-2 whitespace-pre-wrap">
              {data.llm_recommendation}
            </p>
          )}
        </div>
      )}

      {/* Per-skill results */}
      <div className="space-y-2">
        {data.skill_impacts.map((r) => (
          <div key={r.skill_name} className="p-3 border rounded-lg">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">{r.skill_name}</span>
              <span className="text-sm font-bold text-green-600 tabular-nums">
                +{(r.class_gain * 100).toFixed(1)}%
              </span>
            </div>
            <div className="flex gap-4 text-xs text-muted-foreground">
              <span>Current: {(r.current_avg_mastery * 100).toFixed(0)}%</span>
              <span>→ Simulated: {(r.simulated_avg_mastery * 100).toFixed(0)}%</span>
              <span>{r.students_helped} students benefit</span>
            </div>
            {/* Visual bar */}
            <div className="mt-2 flex gap-1 items-center">
              <div className="h-1.5 rounded-full bg-muted flex-1 relative overflow-hidden">
                <div
                  className="absolute left-0 top-0 h-full bg-gray-300 rounded-full"
                  style={{ width: `${r.current_avg_mastery * 100}%` }}
                />
                <div
                  className="absolute left-0 top-0 h-full bg-green-400 rounded-full opacity-60"
                  style={{ width: `${r.simulated_avg_mastery * 100}%` }}
                />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function WhatIfPanel({ courseId }: { courseId: number }) {
  const [mode, setMode] = useState<'manual' | 'automatic'>('automatic');
  const [manualSkills, setManualSkills] = useState<WhatIfSkillInput[]>([
    { skill_name: '', hypothetical_mastery: 0.8 },
  ]);
  const [topK, setTopK] = useState(5);
  const [targetGain, setTargetGain] = useState(0.1);
  const [enableLlm, setEnableLlm] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<WhatIfResponse | null>(null);
  const [selectedSkillNames, setSelectedSkillNames] = useState<string[]>([]);
  const storageKey = `teacher_whatif_${courseId}`;

  const addSkill = () =>
    setManualSkills((prev) => [...prev, { skill_name: '', hypothetical_mastery: 0.8 }]);

  const removeSkill = (i: number) =>
    setManualSkills((prev) => prev.filter((_, idx) => idx !== i));

  const updateSkill = (i: number, field: keyof WhatIfSkillInput, value: string | number) =>
    setManualSkills((prev) =>
      prev.map((sk, idx) => (idx === i ? { ...sk, [field]: value } : sk))
    );

  const run = async () => {
    setLoading(true);
    try {
      const manualPayload =
        mode === 'manual'
          ? [
              ...manualSkills.filter((s) => s.skill_name.trim()),
              ...selectedSkillNames
                .filter((name) => !manualSkills.some((s) => s.skill_name.trim() === name))
                .map((name) => ({ skill_name: name, hypothetical_mastery: 0.8 })),
            ]
          : undefined;
      const resp = await teacherTwinApi.runWhatIf(courseId, {
        mode,
        skills: manualPayload,
        top_k: topK,
        target_gain: targetGain,
        enable_llm: enableLlm,
      });
      setResult(resp.data);
      try {
        localStorage.setItem(
          storageKey,
          JSON.stringify({
            mode,
            topK,
            targetGain,
            manualSkills,
            selectedSkillNames,
            enableLlm,
            result: resp.data,
            savedAt: Date.now(),
          })
        );
      } catch {
        // ignore localStorage quota errors
      }
    } catch {
      toast.error('Simulation failed');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return;
      const saved = JSON.parse(raw);
      setMode(saved.mode ?? 'automatic');
      setTopK(saved.topK ?? 5);
      setTargetGain(saved.targetGain ?? 0.1);
      setManualSkills(saved.manualSkills ?? [{ skill_name: '', hypothetical_mastery: 0.8 }]);
      setSelectedSkillNames(saved.selectedSkillNames ?? []);
      setEnableLlm(saved.enableLlm ?? true);
      setResult(saved.result ?? null);
    } catch {
      // ignore corrupted state
    }
  }, [storageKey]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-yellow-500" />
          What-If Forward Simulation
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          ClassGain(s) = Σᵢ (min(1, mᵢₛ + Δ) − mᵢₛ) — explore curriculum impact without affecting students
        </p>
      </CardHeader>
      <CardContent>
        {/* Mode toggle */}
        <div className="flex gap-2 mb-4">
          <Button
            size="sm"
            variant={mode === 'automatic' ? 'default' : 'outline'}
            onClick={() => { setMode('automatic'); setResult(null); }}
          >
            <Sparkles className="h-3 w-3 mr-1" />
            Automatic
          </Button>
          <Button
            size="sm"
            variant={mode === 'manual' ? 'default' : 'outline'}
            onClick={() => { setMode('manual'); setResult(null); }}
          >
            <PlayCircle className="h-3 w-3 mr-1" />
            Manual
          </Button>
        </div>

        {/* Automatic mode controls */}
        {mode === 'automatic' && (
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Top-K skills to evaluate ({topK})</Label>
              <Slider
                min={2}
                max={15}
                step={1}
                value={[topK]}
                onValueChange={([v]) => setTopK(v)}
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Target mastery gain per student ({(targetGain * 100).toFixed(0)}%)</Label>
              <Slider
                min={0.05}
                max={0.5}
                step={0.05}
                value={[targetGain]}
                onValueChange={([v]) => setTargetGain(v)}
                className="mt-1"
              />
            </div>
          </div>
        )}

        {/* Manual mode controls */}
        {mode === 'manual' && (
          <div className="space-y-2">
            {result?.skill_impacts?.length ? (
              <div className="p-2 rounded border bg-muted/20">
                <Label className="text-xs">Pick skills from latest simulation (optional)</Label>
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {result.skill_impacts.map((skill) => {
                    const selected = selectedSkillNames.includes(skill.skill_name);
                    return (
                      <button
                        key={skill.skill_name}
                        className={`text-[11px] px-2 py-1 rounded border ${
                          selected ? 'bg-primary text-primary-foreground border-primary' : 'border-border'
                        }`}
                        onClick={() =>
                          setSelectedSkillNames((prev) =>
                            prev.includes(skill.skill_name)
                              ? prev.filter((name) => name !== skill.skill_name)
                              : [...prev, skill.skill_name]
                          )
                        }
                      >
                        {skill.skill_name}
                      </button>
                    );
                  })}
                </div>
              </div>
            ) : null}
            {manualSkills.map((sk, i) => (
              <div key={i} className="flex gap-2 items-center">
                <Input
                  placeholder="Skill name"
                  value={sk.skill_name}
                  onChange={(e) => updateSkill(i, 'skill_name', e.target.value)}
                  className="flex-1 h-8 text-sm"
                />
                <div className="flex items-center gap-1">
                  <span className="text-xs text-muted-foreground w-5 text-right">
                    {((sk.hypothetical_mastery ?? 0.8) * 100).toFixed(0)}%
                  </span>
                  <input
                    type="range"
                    min="0.1"
                    max="1"
                    step="0.05"
                    value={sk.hypothetical_mastery ?? 0.8}
                    onChange={(e) => updateSkill(i, 'hypothetical_mastery', parseFloat(e.target.value))}
                    className="w-20"
                  />
                </div>
                {manualSkills.length > 1 && (
                  <button onClick={() => removeSkill(i)} className="text-muted-foreground hover:text-destructive">
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
            <Button size="sm" variant="ghost" onClick={addSkill} className="text-xs h-7">
              <Plus className="h-3 w-3 mr-1" /> Add skill
            </Button>
          </div>
        )}

        <div className="mt-3 flex items-center gap-2">
          <input
            id="whatif-llm"
            type="checkbox"
            checked={enableLlm}
            onChange={(e) => setEnableLlm(e.target.checked)}
          />
          <Label htmlFor="whatif-llm" className="text-xs">
            Include LLM strategic recommendation
          </Label>
        </div>

        {/* Run button */}
        <Button className="mt-4 w-full" onClick={run} disabled={loading}>
          {loading ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Simulating…</>
          ) : (
            <><PlayCircle className="h-4 w-4 mr-2" /> Run Simulation</>
          )}
        </Button>

        {/* Results */}
        {result && <SimulationResults data={result} />}
      </CardContent>
    </Card>
  );
}
