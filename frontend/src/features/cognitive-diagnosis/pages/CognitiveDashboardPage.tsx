import { useState, useCallback, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Loader2,
  Brain,
  Map,
  Repeat2,
  Dumbbell,
  Activity,
  RefreshCw,
  Fingerprint,
} from 'lucide-react';
import { toast } from 'sonner';
import { diagnosisApi } from '../api';
import type { PortfolioResponse, ReviewResponse } from '../api';
import { useAuth } from '@/features/auth/context/AuthContext';
import { MasteryBar } from '../components/MasteryBar';
import { LearningPathPanel } from '../components/LearningPathPanel';
import { ExercisePanel } from '../components/ExercisePanel';
import { RevFellPanel } from '../components/RevFellPanel';
import { OrchestratorPanel } from '../components/OrchestratorPanel';
import { DigitalTwinTab } from '../components/DigitalTwinTab';

type AgentTab = 'assess' | 'pathgen' | 'revfell' | 'adaex' | 'orchestrator' | 'digital-twin';

const VALID_TABS: AgentTab[] = ['assess', 'pathgen', 'revfell', 'adaex', 'orchestrator', 'digital-twin'];

export default function CognitiveDashboardPage() {
  const { user } = useAuth();
  const { id: courseIdStr } = useParams<{ id: string }>();
  const courseId = Number(courseIdStr);
  const [searchParams, setSearchParams] = useSearchParams();

  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null);
  const [loadingPortfolio, setLoadingPortfolio] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  // Read initial tab from URL ?tab=xxx, fall back to 'digital-twin' as default entry
  const tabFromUrl = searchParams.get('tab') as AgentTab | null;
  const initialTab: AgentTab =
    tabFromUrl && VALID_TABS.includes(tabFromUrl) ? tabFromUrl : 'assess';

  const [activeTab, setActiveTab] = useState<AgentTab>(initialTab);
  const isTeacher = user?.role === 'teacher';

  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);

  // RevFell lazy-load
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [loadingReview, setLoadingReview] = useState(false);
  const [reviewLoaded, setReviewLoaded] = useState(false);

  const loadPortfolio = useCallback(async () => {
    if (!courseId) return;
    setLoadingPortfolio(true);
    try {
      const resp = await diagnosisApi.getPortfolio(courseId);
      setPortfolio(resp.data);
    } catch {
      toast.error('Failed to load ARCD portfolio');
    } finally {
      setLoadingPortfolio(false);
    }
  }, [courseId]);

  useEffect(() => {
    loadPortfolio();
  }, [loadPortfolio]);

  // Sync URL when tab changes + lazy-load RevFell review
  const handleTabChange = async (tab: string) => {
    const t = tab as AgentTab;
    if (!isTeacher) return;
    setActiveTab(t);
    setSearchParams({ tab }, { replace: true });
    if (tab === 'revfell' && !reviewLoaded && portfolio) {
      setLoadingReview(true);
      try {
        const resp = await diagnosisApi.getReview(courseId, 8);
        setReview(resp.data);
        setReviewLoaded(true);
      } catch {
        toast.error('Failed to load review session');
      } finally {
        setLoadingReview(false);
      }
    }
  };

  const recompute = async () => {
    if (!courseId) return;
    setRecomputing(true);
    try {
      await diagnosisApi.computeMastery(courseId);
      await loadPortfolio();
      // Invalidate review cache so it reloads with fresh data
      setReviewLoaded(false);
      setReview(null);
      toast.success('ARCD portfolio updated');
    } catch {
      toast.error('Failed to recompute mastery');
    } finally {
      setRecomputing(false);
    }
  };

  const handlePracticeSkill = (skillName: string) => {
    setSelectedSkill(skillName);
    setActiveTab('adaex');
    setSearchParams({ tab: 'adaex' }, { replace: true });
  };

  // ── Loading state ──────────────────────────────────────────────────────
  if (loadingPortfolio && !portfolio) {
    return (
      <Card>
        <CardContent className="py-16 flex flex-col items-center gap-3">
          <Loader2 className="h-10 w-10 text-primary animate-spin" />
          <p className="text-sm text-muted-foreground">Loading your ARCD dashboard…</p>
        </CardContent>
      </Card>
    );
  }

  // ── Empty state ────────────────────────────────────────────────────────
  if (!portfolio && !loadingPortfolio) {
    return (
      <Card>
        <CardContent className="py-16 text-center space-y-3">
          <Brain className="h-10 w-10 text-muted-foreground mx-auto" />
          <p className="text-sm font-medium">No ARCD Data Yet</p>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            Select and lock your skills in the <strong>Learning Path</strong> page first.
            Once locked, ARCD will track only your chosen skills and generate a personalised
            mastery profile.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (!portfolio) return null;

  if (!isTeacher) {
    return (
      <Card>
        <CardContent className="py-16 text-center space-y-3">
          <Brain className="h-10 w-10 text-muted-foreground mx-auto" />
          <p className="text-sm font-medium">This dashboard is for teachers</p>
          <p className="text-xs text-muted-foreground max-w-sm mx-auto">
            Students can continue learning from the ARCD student pages and review sessions.
          </p>
        </CardContent>
      </Card>
    );
  }

  const stats = portfolio.stats;
  const masteredPct = stats.total_skills
    ? ((stats.mastered_skills / stats.total_skills) * 100).toFixed(0)
    : '0';

  // ── Main dashboard ─────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Brain className="h-6 w-6 text-primary" />
            ARCD Agent Dashboard
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Multi-agent adaptive learning — Assess → PathGen → RevFell → AdaEx
            {portfolio.mastery.length > 0 && (
              <span className="ml-2 inline-flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400">
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500" />
                {portfolio.mastery.length} selected skill{portfolio.mastery.length !== 1 ? 's' : ''}
              </span>
            )}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={recompute} disabled={recomputing}>
          {recomputing ? (
            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4 mr-1" />
          )}
          Recompute
        </Button>
      </div>

      {/* Quick stats strip */}
      <div className="grid grid-cols-4 gap-2">
        <StripStat label="Skills" value={stats.total_skills} />
        <StripStat label="Mastered" value={`${masteredPct}%`} highlight="green" />
        <StripStat label="Avg Mastery" value={`${(stats.average_mastery * 100).toFixed(0)}%`} highlight="blue" />
        <StripStat label="PCO Risks" value={stats.pco_count} highlight={stats.pco_count > 0 ? 'orange' : undefined} />
      </div>

      {/* 5-agent tabs */}
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList className="w-full justify-start overflow-x-auto">
          <TabsTrigger value="assess" className="flex items-center gap-1.5">
            <Brain className="h-3 w-3" />
            <span>Mastery</span>
            <span className="hidden sm:inline text-xs text-muted-foreground">(Assess)</span>
          </TabsTrigger>
          <TabsTrigger value="pathgen" className="flex items-center gap-1.5">
            <Map className="h-3 w-3" />
            <span>PathGen</span>
          </TabsTrigger>
          <TabsTrigger value="revfell" className="flex items-center gap-1.5">
            <Repeat2 className="h-3 w-3" />
            <span>RevFell</span>
            {portfolio.pco_skills.length > 0 && (
              <span className="ml-0.5 h-4 min-w-4 px-1 rounded-full bg-destructive text-destructive-foreground text-xs flex items-center justify-center">
                {portfolio.pco_skills.length}
              </span>
            )}
          </TabsTrigger>
          <TabsTrigger value="adaex" className="flex items-center gap-1.5">
            <Dumbbell className="h-3 w-3" />
            <span>AdaEx</span>
          </TabsTrigger>
          <TabsTrigger value="orchestrator" className="flex items-center gap-1.5">
            <Activity className="h-3 w-3" />
            <span>Orchestrator</span>
          </TabsTrigger>
          <TabsTrigger value="digital-twin" className="flex items-center gap-1.5">
            <Fingerprint className="h-3 w-3" />
            <span>Digital Twin</span>
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Assess / Mastery ─────────────────────────────────── */}
        <TabsContent value="assess" className="mt-4">
          <AssessTab portfolio={portfolio} onPracticeSkill={handlePracticeSkill} />
        </TabsContent>

        {/* ── Tab 2: PathGen ──────────────────────────────────────────── */}
        <TabsContent value="pathgen" className="mt-4">
          <LearningPathPanel
            path={portfolio.learning_path}
            onSelectSkill={(name) => {
              setSelectedSkill(name);
              setActiveTab('adaex');
            }}
          />
        </TabsContent>

        {/* ── Tab 3: RevFell ──────────────────────────────────────────── */}
        <TabsContent value="revfell" className="mt-4">
          <RevFellPanel
            review={review}
            pcoSkillsFromPortfolio={portfolio.pco_skills}
            loading={loadingReview}
            onPracticeSkill={handlePracticeSkill}
          />
        </TabsContent>

        {/* ── Tab 4: AdaEx ────────────────────────────────────────────── */}
        <TabsContent value="adaex" className="mt-4">
          <AdaExTab
            portfolio={portfolio}
            selectedSkill={selectedSkill}
            onSelectSkill={setSelectedSkill}
            courseId={courseId}
          />
        </TabsContent>

        {/* ── Tab 5: Orchestrator ─────────────────────────────────────── */}
        <TabsContent value="orchestrator" className="mt-4">
          <OrchestratorPanel portfolio={portfolio} />
        </TabsContent>

        {/* ── Tab 6: Digital Twin ──────────────────────────────────────── */}
        <TabsContent value="digital-twin" className="mt-4">
          <DigitalTwinTab
            portfolio={portfolio}
            onPracticeSkill={handlePracticeSkill}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ── Assess tab ─────────────────────────────────────────────────────────────

function AssessTab({
  portfolio,
  onPracticeSkill,
}: {
  portfolio: PortfolioResponse;
  onPracticeSkill: (name: string) => void;
}) {
  const grouped = {
    above: portfolio.mastery.filter((s) => s.status === 'above'),
    at: portfolio.mastery.filter((s) => s.status === 'at'),
    below: portfolio.mastery.filter((s) => s.status === 'below'),
    not_started: portfolio.mastery.filter((s) => s.status === 'not_started'),
  };

  if (portfolio.mastery.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No skills tracked yet. Select skills in your learning path first.
        </CardContent>
      </Card>
    );
  }

  const sections = [
    { key: 'above', label: 'Mastered', count: grouped.above.length, accent: 'text-green-600 dark:text-green-400' },
    { key: 'at', label: 'In Progress (ZPD)', count: grouped.at.length, accent: 'text-blue-600 dark:text-blue-400' },
    { key: 'below', label: 'Learning', count: grouped.below.length, accent: 'text-orange-600 dark:text-orange-400' },
    { key: 'not_started', label: 'Not Started', count: grouped.not_started.length, accent: 'text-muted-foreground' },
  ] as const;

  return (
    <div className="space-y-4">
      {sections.map((sec) => {
        const skills = grouped[sec.key];
        if (skills.length === 0) return null;
        return (
          <Card key={sec.key}>
            <CardContent className="pt-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className={`text-sm font-semibold ${sec.accent}`}>
                  {sec.label}
                  <span className="ml-1 text-muted-foreground font-normal">({sec.count})</span>
                </h3>
              </div>
              <div className="space-y-3">
                {skills.map((skill) => (
                  <div key={skill.skill_name} className="group">
                    <MasteryBar skill={skill} />
                    {sec.key !== 'not_started' && (
                      <button
                        className="mt-1 text-xs text-muted-foreground group-hover:text-primary transition-colors"
                        onClick={() => onPracticeSkill(skill.skill_name)}
                      >
                        Practice →
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

// ── AdaEx tab ──────────────────────────────────────────────────────────────

function AdaExTab({
  portfolio,
  selectedSkill,
  onSelectSkill,
  courseId,
}: {
  portfolio: PortfolioResponse;
  selectedSkill: string | null;
  onSelectSkill: (name: string) => void;
  courseId: number;
}) {
  return (
    <div className="space-y-4">
      {/* Difficulty profile hint for selected skill */}
      {selectedSkill && (() => {
        const skill = portfolio.mastery.find((s) => s.skill_name === selectedSkill);
        if (!skill) return null;
        const mastery = skill.mastery;
        // Estimate ZPD-based difficulty target: d* = mastery + 0.2, clamped [0.1, 0.9]
        const targetD = Math.min(0.9, Math.max(0.1, mastery + 0.2));
        const band = targetD < 0.35 ? 'Easy' : targetD < 0.65 ? 'Medium' : 'Hard';
        const zpd = mastery < 0.4 ? 'below' : mastery < 0.9 ? 'in' : 'above';
        return (
          <Card className="border-dashed">
            <CardContent className="pt-4 pb-3">
              <div className="flex flex-wrap items-center gap-4 text-xs">
                <span className="font-semibold text-sm">{selectedSkill}</span>
                <span className="text-muted-foreground">
                  Mastery: <strong>{(mastery * 100).toFixed(0)}%</strong>
                </span>
                <span className="text-muted-foreground">
                  Target difficulty: <strong>{targetD.toFixed(2)}</strong>
                </span>
                <span className="text-muted-foreground">
                  Band: <strong>{band}</strong>
                </span>
                <span className="text-muted-foreground">
                  ZPD position: <strong>{zpd}</strong>
                </span>
              </div>
            </CardContent>
          </Card>
        );
      })()}

      {/* Skill selector chips */}
      <Card>
        <CardContent className="pt-4 pb-3">
          <p className="text-xs text-muted-foreground mb-2">Select a skill to practice:</p>
          <div className="flex flex-wrap gap-1.5">
            {portfolio.mastery.map((s) => (
              <button
                key={s.skill_name}
                onClick={() => onSelectSkill(s.skill_name)}
                className={`px-2.5 py-1 rounded-full text-xs transition-colors border ${
                  selectedSkill === s.skill_name
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'border-border hover:border-primary/50 hover:bg-muted/50'
                }`}
              >
                {s.skill_name}
                <span className="ml-1 opacity-60 tabular-nums">
                  {(s.mastery * 100).toFixed(0)}%
                </span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Exercise */}
      {selectedSkill ? (
        <ExercisePanel
          skillName={selectedSkill}
          courseId={courseId}
          onAnswer={(isCorrect) => {
            if (isCorrect) {
              toast.success('Correct! Great work.');
            } else {
              toast('Incorrect — review the concept and try again.');
            }
          }}
        />
      ) : (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground text-sm">
            Select a skill above to generate an adaptive exercise.
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ── Strip stat ─────────────────────────────────────────────────────────────

function StripStat({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string | number;
  highlight?: 'green' | 'blue' | 'orange';
}) {
  const colors = {
    green: 'text-green-600 dark:text-green-400',
    blue: 'text-blue-600 dark:text-blue-400',
    orange: 'text-orange-500',
  };
  return (
    <Card>
      <CardContent className="pt-3 pb-3 text-center">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={`text-xl font-bold tabular-nums ${highlight ? colors[highlight] : ''}`}>
          {value}
        </p>
      </CardContent>
    </Card>
  );
}
