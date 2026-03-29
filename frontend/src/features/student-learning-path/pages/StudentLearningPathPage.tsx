import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { BookOpen, Video, HelpCircle, Sparkles, CheckCircle2, Users, ExternalLink, Loader2 } from 'lucide-react';
import {
  getSkillBanks,
  selectSkills,
  deselectSkills,
  buildLearningPath,
  getLearningPath,
  streamBuildProgress,
  type SkillBanksResponse,
  type LearningPathResponse,
  type BuildProgressEvent,
} from '../api';

export default function StudentLearningPathPage() {
  const { id: courseId } = useParams<{ id: string }>();
  const numericCourseId = Number(courseId);

  const [activeTab, setActiveTab] = useState<'select' | 'path'>('select');
  const [skillBanks, setSkillBanks] = useState<SkillBanksResponse | null>(null);
  const [learningPath, setLearningPath] = useState<LearningPathResponse | null>(null);
  const [selectedSkills, setSelectedSkills] = useState<Set<string>>(new Set());
  const [isBuilding, setIsBuilding] = useState(false);
  const [buildProgress, setBuildProgress] = useState<BuildProgressEvent[]>([]);
  const [buildPercent, setBuildPercent] = useState(0);
  const [loading, setLoading] = useState(true);

  // Load skill banks
  const loadSkillBanks = useCallback(async () => {
    try {
      const data = await getSkillBanks(numericCourseId);
      setSkillBanks(data);
      setSelectedSkills(new Set(data.selected_skill_names));
    } catch (err) {
      toast.error('Failed to load skill banks');
      console.error(err);
    }
  }, [numericCourseId]);

  // Load learning path
  const loadLearningPath = useCallback(async () => {
    try {
      const data = await getLearningPath(numericCourseId);
      setLearningPath(data);
    } catch {
      // If no path yet, that's okay
    }
  }, [numericCourseId]);

  useEffect(() => {
    async function init() {
      setLoading(true);
      await Promise.all([loadSkillBanks(), loadLearningPath()]);
      setLoading(false);
    }
    init();
  }, [loadSkillBanks, loadLearningPath]);

  const toggleSkill = async (skillName: string, source: 'book' | 'market') => {
    const isSelected = selectedSkills.has(skillName);
    try {
      if (isSelected) {
        await deselectSkills(numericCourseId, [skillName]);
        setSelectedSkills(prev => {
          const next = new Set(prev);
          next.delete(skillName);
          return next;
        });
      } else {
        await selectSkills(numericCourseId, [skillName], source);
        setSelectedSkills(prev => new Set(prev).add(skillName));
      }
    } catch {
      toast.error(`Failed to ${isSelected ? 'deselect' : 'select'} skill`);
    }
  };

  const handleBuild = async () => {
    if (selectedSkills.size === 0) {
      toast.warning('Select at least one skill first');
      return;
    }

    setIsBuilding(true);
    setBuildProgress([]);
    setBuildPercent(0);

    try {
      const { run_id } = await buildLearningPath(numericCourseId);

      streamBuildProgress(
        numericCourseId,
        run_id,
        (event) => {
          setBuildProgress(prev => [...prev, event]);
          if (event.total_skills > 0) {
            setBuildPercent(Math.round((event.skills_completed / event.total_skills) * 100));
          }
        },
        async () => {
          setIsBuilding(false);
          setBuildPercent(100);
          toast.success('Learning path built successfully!');
          await loadLearningPath();
          setActiveTab('path');
        },
        (err) => {
          setIsBuilding(false);
          toast.error(`Build failed: ${err.message}`);
        },
      );
    } catch {
      setIsBuilding(false);
      toast.error('Failed to start build');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 h-full overflow-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">My Learning Path</h1>
          <p className="text-muted-foreground">
            Select skills you want to master, then build your personalized learning path.
          </p>
        </div>
        <Button
          onClick={handleBuild}
          disabled={isBuilding || selectedSkills.size === 0}
          size="lg"
          className="gap-2"
        >
          {isBuilding ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Sparkles className="h-4 w-4" />
          )}
          {isBuilding ? 'Building...' : 'Build My Learning Path'}
        </Button>
      </div>

      {/* Build Progress */}
      {isBuilding && (
        <Card className="border-primary/20 bg-primary/5">
          <CardContent className="pt-6">
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">Building your learning path...</span>
                <span className="text-muted-foreground">{buildPercent}%</span>
              </div>
              <Progress value={buildPercent} className="h-2" />
              {buildProgress.length > 0 && (
                <p className="text-xs text-muted-foreground">
                  {buildProgress[buildProgress.length - 1].detail}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as 'select' | 'path')}>
        <TabsList>
          <TabsTrigger value="select" className="gap-2">
            <CheckCircle2 className="h-4 w-4" />
            Select Skills
            {selectedSkills.size > 0 && (
              <Badge variant="secondary" className="ml-1">{selectedSkills.size}</Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="path" className="gap-2">
            <BookOpen className="h-4 w-4" />
            Learning Path
            {learningPath && learningPath.total_selected_skills > 0 && (
              <Badge variant="secondary" className="ml-1">
                {learningPath.skills_with_resources}/{learningPath.total_selected_skills}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        {/* SELECT SKILLS TAB */}
        <TabsContent value="select" className="mt-4">
          <div className="text-sm text-muted-foreground mb-4">
            Click skills to select or deselect them. Skills selected by your peers are
            marked with a <Users className="inline h-3 w-3" /> badge.
          </div>
          {skillBanks && (
            <div className="flex flex-wrap gap-2">
              {/* Render book + market skills from peer_selection_counts as flat list */}
              {Object.entries(skillBanks.peer_selection_counts).map(([name, count]) => {
                const isSelected = selectedSkills.has(name);
                const source = skillBanks.selected_map[name] || 'book';
                return (
                  <Button
                    key={name}
                    variant={isSelected ? 'default' : 'outline'}
                    size="sm"
                    className="gap-1.5 transition-all"
                    onClick={() => toggleSkill(name, source as 'book' | 'market')}
                  >
                    {isSelected && <CheckCircle2 className="h-3.5 w-3.5" />}
                    {name}
                    {count > 0 && (
                      <Badge variant="secondary" className="ml-1 text-xs py-0 px-1">
                        <Users className="h-3 w-3 mr-0.5" />
                        {count}
                      </Badge>
                    )}
                  </Button>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* LEARNING PATH TAB */}
        <TabsContent value="path" className="mt-4">
          {!learningPath || learningPath.chapters.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-center text-muted-foreground">
                <Sparkles className="h-10 w-10 mx-auto mb-3 text-muted-foreground/50" />
                <p>No learning path yet. Select skills and click "Build My Learning Path" to get started.</p>
              </CardContent>
            </Card>
          ) : (
            <Accordion type="multiple" defaultValue={learningPath.chapters.map((_, i) => `ch-${i}`)}>
              {learningPath.chapters.map((chapter, chIdx) => (
                <AccordionItem key={chIdx} value={`ch-${chIdx}`}>
                  <AccordionTrigger className="text-lg font-semibold">
                    Chapter {chapter.chapter_index}: {chapter.title}
                    <Badge variant="outline" className="ml-2">{chapter.selected_skills.length} skills</Badge>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="flex flex-col gap-4 pl-4">
                      {chapter.selected_skills.map((skill) => (
                        <Card key={skill.name} className="overflow-hidden">
                          <CardHeader className="pb-2">
                            <div className="flex items-center justify-between">
                              <CardTitle className="text-base">{skill.name}</CardTitle>
                              <Badge variant={skill.resource_status === 'loaded' ? 'default' : 'secondary'}>
                                {skill.resource_status === 'loaded' ? 'Ready' : 'Pending'}
                              </Badge>
                            </div>
                            {skill.description && (
                              <CardDescription>{skill.description}</CardDescription>
                            )}
                          </CardHeader>
                          <CardContent className="space-y-4">
                            {/* Readings */}
                            {skill.readings.length > 0 && (
                              <div>
                                <h4 className="text-sm font-medium flex items-center gap-1.5 mb-2">
                                  <BookOpen className="h-4 w-4 text-blue-500" />
                                  Reading Resources
                                </h4>
                                <div className="grid gap-2">
                                  {skill.readings.map((r, i) => (
                                    <a
                                      key={i}
                                      href={r.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="flex items-start gap-2 p-2 rounded-md border hover:bg-accent transition-colors text-sm"
                                    >
                                      <ExternalLink className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                                      <div className="min-w-0">
                                        <p className="font-medium truncate">{r.title}</p>
                                        <p className="text-xs text-muted-foreground truncate">{r.domain}</p>
                                      </div>
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Videos */}
                            {skill.videos.length > 0 && (
                              <div>
                                <h4 className="text-sm font-medium flex items-center gap-1.5 mb-2">
                                  <Video className="h-4 w-4 text-red-500" />
                                  Video Resources
                                </h4>
                                <div className="grid gap-2">
                                  {skill.videos.map((v, i) => (
                                    <a
                                      key={i}
                                      href={v.url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="flex items-start gap-2 p-2 rounded-md border hover:bg-accent transition-colors text-sm"
                                    >
                                      <Video className="h-4 w-4 mt-0.5 text-muted-foreground shrink-0" />
                                      <div className="min-w-0">
                                        <p className="font-medium truncate">{v.title}</p>
                                        <p className="text-xs text-muted-foreground truncate">{v.domain}</p>
                                      </div>
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Questions */}
                            {skill.questions.length > 0 && (
                              <>
                                <Separator />
                                <div>
                                  <h4 className="text-sm font-medium flex items-center gap-1.5 mb-2">
                                    <HelpCircle className="h-4 w-4 text-amber-500" />
                                    Self-Assessment Questions
                                  </h4>
                                  <div className="flex flex-col gap-2">
                                    {skill.questions.map((q, i) => (
                                      <QuestionCard key={i} question={q} />
                                    ))}
                                  </div>
                                </div>
                              </>
                            )}
                          </CardContent>
                        </Card>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function QuestionCard({ question }: { question: { text: string; difficulty: string; answer: string } }) {
  const [showAnswer, setShowAnswer] = useState(false);
  const difficultyColors: Record<string, string> = {
    easy: 'bg-green-500/10 text-green-700 dark:text-green-400',
    medium: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
    hard: 'bg-red-500/10 text-red-700 dark:text-red-400',
  };

  return (
    <div className="rounded-md border p-3 space-y-2">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm">{question.text}</p>
        <Badge className={`shrink-0 ${difficultyColors[question.difficulty] || ''}`}>
          {question.difficulty}
        </Badge>
      </div>
      <Button variant="ghost" size="sm" onClick={() => setShowAnswer(!showAnswer)}>
        {showAnswer ? 'Hide Answer' : 'Show Answer'}
      </Button>
      {showAnswer && (
        <p className="text-sm text-muted-foreground bg-muted p-2 rounded-md animate-in fade-in-0 slide-in-from-top-1">
          {question.answer}
        </p>
      )}
    </div>
  );
}
