import {
  type ReactNode,
  useCallback,
  useDeferredValue,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import {
  BookOpen,
  Briefcase,
  Building2,
  CheckCircle2,
  ExternalLink,
  Globe,
  HelpCircle,
  Library,
  Loader2,
  Search,
  Sparkles,
  Users,
  Video,
} from 'lucide-react';
import {
  buildLearningPath,
  getLearningPath,
  getSkillBanks,
  streamBuildProgress,
  type BuildSelectedSkillInput,
  type BuildProgressEvent,
  type LearningPathResponse,
  type PrerequisiteEdge,
  type SkillBanksResponse,
  type StudentSkillBankBook,
  type StudentSkillBankJobPosting,
  type StudentSkillBankSkill,
} from '../api';
import {
  PrerequisiteReviewDialog,
  type PrerequisiteReviewItem,
} from '../components/PrerequisiteReviewDialog';

const DEFAULT_SELECTION_RANGE = {
  min_skills: 20,
  max_skills: 35,
  is_default: true,
} as const;

function getErrorStatus(error: unknown): number | null {
  if (!error || typeof error !== 'object' || !('response' in error)) {
    return null;
  }

  const response = (error as { response?: { status?: unknown } }).response;
  return typeof response?.status === 'number' ? response.status : null;
}

export default function StudentLearningPathPage() {
  const { id: courseId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const numericCourseId = Number(courseId);

  const [skillBanks, setSkillBanks] = useState<SkillBanksResponse | null>(null);
  const [learningPath, setLearningPath] = useState<LearningPathResponse | null>(null);
  const [draftSelectedSkills, setDraftSelectedSkills] = useState<Map<string, 'book' | 'market'>>(
    new Map(),
  );
  const [interestedPostings, setInterestedPostings] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState('');
  const [showSelectedOnly, setShowSelectedOnly] = useState(false);
  const [isBuilding, setIsBuilding] = useState(false);
  const [buildProgress, setBuildProgress] = useState<BuildProgressEvent[]>([]);
  const [buildPercent, setBuildPercent] = useState(0);
  const [loading, setLoading] = useState(true);
  const [acknowledgedKnownSkills, setAcknowledgedKnownSkills] = useState<Set<string>>(new Set());
  const [prerequisiteReviewOpen, setPrerequisiteReviewOpen] = useState(false);
  const buildHadQuestionErrorsRef = useRef(false);
  const buildCompletedSkillsRef = useRef(0);

  const deferredSearchQuery = useDeferredValue(searchQuery.trim().toLowerCase());

  const loadSkillBanks = useCallback(async () => {
    try {
      const data = await getSkillBanks(numericCourseId);
      const nextInterestedPostings = new Set(data.interested_posting_urls);

      setSkillBanks(data);
      setInterestedPostings(nextInterestedPostings);
      return data;
    } catch (err) {
      if (getErrorStatus(err) === 403) {
        setSkillBanks(null);
        setLearningPath(null);
        toast.error('Join the course before opening the learning path.');
        navigate(`/courses/${numericCourseId}`, { replace: true });
        return null;
      }

      toast.error('Failed to load skill banks');
      console.error(err);
      return null;
    }
  }, [navigate, numericCourseId]);

  const loadLearningPath = useCallback(async () => {
    try {
      const data = await getLearningPath(numericCourseId);
      setLearningPath(data);
      return data;
    } catch {
      // If no path exists yet, keep the empty state.
      return null;
    }
  }, [numericCourseId]);

  useEffect(() => {
    async function init() {
      setLoading(true);
      const nextSkillBanks = await loadSkillBanks();
      if ((nextSkillBanks?.selected_skill_names.length ?? 0) > 0) {
        await loadLearningPath();
      } else {
        setLearningPath(null);
      }
      setLoading(false);
    }

    init();
  }, [loadLearningPath, loadSkillBanks]);

  const persistedSelectedSkills = useMemo(
    () => new Set(skillBanks?.selected_skill_names ?? []),
    [skillBanks?.selected_skill_names],
  );
  const selectionLocked = persistedSelectedSkills.size > 0;
  const selectedSkills = useMemo(
    () =>
      new Set(
        selectionLocked ? Array.from(persistedSelectedSkills) : Array.from(draftSelectedSkills.keys()),
      ),
    [draftSelectedSkills, persistedSelectedSkills, selectionLocked],
  );
  const selectionRange = skillBanks?.selection_range ?? DEFAULT_SELECTION_RANGE;
  const directPrerequisiteIndex = useMemo(
    () => buildPrerequisiteIndex(skillBanks?.prerequisite_edges ?? []),
    [skillBanks?.prerequisite_edges],
  );
  const prerequisiteClosure = useMemo(
    () => collectTransitivePrerequisites(selectedSkills, directPrerequisiteIndex),
    [directPrerequisiteIndex, selectedSkills],
  );
  const activeAcknowledgedKnownSkills = useMemo(() => {
    if (selectionLocked) {
      return new Set<string>();
    }

    return new Set(
      Array.from(acknowledgedKnownSkills).filter(
        (skillName) => prerequisiteClosure.has(skillName) && !selectedSkills.has(skillName),
      ),
    );
  }, [acknowledgedKnownSkills, prerequisiteClosure, selectedSkills, selectionLocked]);
  const unresolvedPrerequisiteItems = useMemo(
    () =>
      buildPrerequisiteReviewItems(
        selectedSkills,
        activeAcknowledgedKnownSkills,
        directPrerequisiteIndex,
      ),
    [activeAcknowledgedKnownSkills, directPrerequisiteIndex, selectedSkills],
  );

  const toggleSkill = useCallback(
    (skillName: string, source: 'book' | 'market') => {
      setDraftSelectedSkills((prev) => {
        const next = new Map(prev);
        if (next.has(skillName)) {
          next.delete(skillName);
        } else {
          next.set(skillName, source);
        }
        return next;
      });
    },
    [],
  );

  const toggleJobPosting = useCallback(
    (posting: StudentSkillBankJobPosting) => {
      setInterestedPostings((prev) => {
        const next = new Set(prev);
        if (next.has(posting.url)) {
          next.delete(posting.url);
        } else {
          next.add(posting.url);
        }
        return next;
      });
    },
    [],
  );

  const buildDraftSelection = useCallback(
    (): BuildSelectedSkillInput[] =>
      Array.from(draftSelectedSkills, ([name, source]) => ({
        name,
        source,
      })),
    [draftSelectedSkills],
  );

  const validateSelectionCount = useCallback(
    (count: number) => {
      if (count < selectionRange.min_skills || count > selectionRange.max_skills) {
        toast.warning(
          `Select between ${selectionRange.min_skills} and ${selectionRange.max_skills} skills before building.`,
        );
        return false;
      }
      return true;
    },
    [selectionRange.max_skills, selectionRange.min_skills],
  );

  const startBuild = useCallback(
    async (stagedSelectedSkills: BuildSelectedSkillInput[]) => {
      setIsBuilding(true);
      setBuildProgress([]);
      setBuildPercent(0);
      buildHadQuestionErrorsRef.current = false;
      buildCompletedSkillsRef.current = 0;

      try {
        const { run_id } = await buildLearningPath(
          numericCourseId,
          selectionLocked ? [] : stagedSelectedSkills,
        );

        streamBuildProgress(
          numericCourseId,
          run_id,
          (event) => {
            if (event.phase === 'question_error') {
              buildHadQuestionErrorsRef.current = true;
            }
            setBuildProgress((prev) => [...prev, event]);
            if (event.total_skills > 0 && (event.phase === 'done' || event.phase === 'skipped')) {
              buildCompletedSkillsRef.current = Math.max(
                buildCompletedSkillsRef.current,
                event.skills_completed,
              );
              setBuildPercent(
                Math.round((buildCompletedSkillsRef.current / event.total_skills) * 100),
              );
            }
          },
          async () => {
            setIsBuilding(false);
            setBuildPercent(100);
            setAcknowledgedKnownSkills(new Set());
            setPrerequisiteReviewOpen(false);
            const updatedSkillBanks = await loadSkillBanks();
            const updatedLearningPath =
              (updatedSkillBanks?.selected_skill_names.length ?? 0) > 0
                ? await loadLearningPath()
                : null;
            const skillsMissingQuestions =
              updatedLearningPath?.chapters.reduce(
                (total, chapter) =>
                  total +
                  chapter.selected_skills.filter((skill) => skill.questions.length === 0).length,
                0,
              ) ?? 0;

            if (skillsMissingQuestions > 0) {
              toast.warning(
                `Learning path built, but ${skillsMissingQuestions} skill${
                  skillsMissingQuestions === 1 ? '' : 's'
                } still have no questions. If you recently changed the backend code, restart it and rebuild.`,
              );
            } else if (buildHadQuestionErrorsRef.current) {
              toast.warning(
                'Learning path built with some question-generation issues. Try rebuilding to backfill missing questions.',
              );
            } else {
              toast.success('Learning path built successfully!');
            }
          },
          async (err) => {
            setIsBuilding(false);
            const updatedSkillBanks = await loadSkillBanks();
            if ((updatedSkillBanks?.selected_skill_names.length ?? 0) > 0) {
              await loadLearningPath();
            } else {
              setLearningPath(null);
            }
            toast.error(`Build failed: ${err.message}`);
          },
        );
      } catch (err) {
        setIsBuilding(false);
        console.error(err);
        const detail =
          err &&
          typeof err === 'object' &&
          'response' in err &&
          typeof (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail ===
            'string'
            ? (err as { response: { data: { detail: string } } }).response.data.detail
            : 'Failed to start build';
        toast.error(detail);
      }
    },
    [loadLearningPath, loadSkillBanks, numericCourseId, selectionLocked],
  );

  const handleBuild = async () => {
    const stagedSelectedSkills = buildDraftSelection();

    if (!selectionLocked && stagedSelectedSkills.length === 0) {
      toast.warning('Select at least one skill first');
      return;
    }

    if (!selectionLocked && unresolvedPrerequisiteItems.length > 0) {
      setPrerequisiteReviewOpen(true);
      return;
    }

    if (!selectionLocked && !validateSelectionCount(stagedSelectedSkills.length)) {
      return;
    }

    await startBuild(stagedSelectedSkills);
  };

  const handleAddPrerequisiteToSelection = useCallback((skillName: string) => {
    const inferredSource = inferPrerequisiteSource(skillName, skillBanks);
    setDraftSelectedSkills((prev) => {
      const next = new Map(prev);
      next.set(skillName, inferredSource);
      return next;
    });
    setAcknowledgedKnownSkills((prev) => {
      if (!prev.has(skillName)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(skillName);
      return next;
    });
  }, [skillBanks]);

  const handleAcknowledgeKnownPrerequisite = useCallback((skillName: string) => {
    setAcknowledgedKnownSkills((prev) => new Set(prev).add(skillName));
  }, []);

  const handleContinueBuildAfterPrerequisiteReview = useCallback(async () => {
    if (unresolvedPrerequisiteItems.length > 0) {
      return;
    }

    const stagedSelectedSkills = buildDraftSelection();
    if (!validateSelectionCount(stagedSelectedSkills.length)) {
      setPrerequisiteReviewOpen(false);
      return;
    }

    setPrerequisiteReviewOpen(false);
    await startBuild(stagedSelectedSkills);
  }, [buildDraftSelection, startBuild, unresolvedPrerequisiteItems.length, validateSelectionCount]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const allBooks = skillBanks?.book_skill_banks ?? [];
  const allMarketPostings = skillBanks?.market_skill_bank ?? [];

  const filteredBookBanks = filterBookSkillBanks(
    allBooks,
    deferredSearchQuery,
    showSelectedOnly,
    selectedSkills,
  );
  const filteredMarketSkillBank = filterMarketSkillBank(
    allMarketPostings,
    deferredSearchQuery,
    showSelectedOnly,
    selectedSkills,
    interestedPostings,
  );

  const totalBookCount = allBooks.length;
  const totalBookChapterCount = allBooks.reduce((total, book) => total + book.chapters.length, 0);
  const totalBookSkillCount = allBooks.reduce(
    (total, book) =>
      total + book.chapters.reduce((chapterTotal, chapter) => chapterTotal + chapter.skills.length, 0),
    0,
  );
  const totalMarketSkillCount = allMarketPostings.reduce(
    (total, posting) => total + posting.skills.length,
    0,
  );

  const visibleBookChapterCount = filteredBookBanks.reduce(
    (total, book) => total + book.chapters.length,
    0,
  );
  const visibleBookSkillCount = filteredBookBanks.reduce(
    (total, book) =>
      total + book.chapters.reduce((chapterTotal, chapter) => chapterTotal + chapter.skills.length, 0),
    0,
  );
  const visibleMarketSkillCount = filteredMarketSkillBank.reduce(
    (total, posting) => total + posting.skills.length,
    0,
  );

  const isSelectionCountInRange =
    selectedSkills.size >= selectionRange.min_skills &&
    selectedSkills.size <= selectionRange.max_skills;
  const selectionStatusLabel = selectionLocked
    ? 'Study mode'
    : `${selectedSkills.size} of ${selectionRange.min_skills}-${selectionRange.max_skills} skills selected`;
  const selectionHelperText = selectionLocked
    ? 'Your saved learning path is ready to study and rebuild when needed.'
    : isSelectionCountInRange
      ? 'Your current draft is within the course range. Build after you review any prerequisite gaps.'
      : selectedSkills.size < selectionRange.min_skills
        ? `Select at least ${selectionRange.min_skills - selectedSkills.size} more skill${
            selectionRange.min_skills - selectedSkills.size === 1 ? '' : 's'
          } before building.`
        : `Remove at least ${selectedSkills.size - selectionRange.max_skills} skill${
            selectedSkills.size - selectionRange.max_skills === 1 ? '' : 's'
          } before building.`;

  return (
    <div className="flex h-full flex-col gap-6 overflow-auto">
      <section className="relative overflow-hidden rounded-3xl border border-border/60 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.14),transparent_34%),radial-gradient(circle_at_bottom_right,rgba(16,185,129,0.14),transparent_32%)] p-6">
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent dark:via-white/15" />
        <div className="relative flex flex-col gap-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-3xl space-y-2">
              <Badge variant="outline" className="rounded-full border-white/20 bg-background/70 px-3 py-1 text-[11px]">
                Personalized Skill Studio
              </Badge>
              <div className="space-y-1">
                <h1 className="text-3xl font-semibold tracking-tight">My Learning Path</h1>
                <p className="max-w-2xl text-sm text-muted-foreground">
                  Browse every linked book, compare it with live job-posting skills, and shape a path
                  that feels tailored instead of generic.
                </p>
              </div>
            </div>

            <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-center">
              <Badge
                variant={selectionLocked || isSelectionCountInRange ? 'outline' : 'secondary'}
                className={cn(
                  'justify-center rounded-full px-3 py-1 text-[11px]',
                  selectionLocked || isSelectionCountInRange
                    ? 'border-white/20 bg-background/70'
                    : 'border-amber-200 bg-amber-100 text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100',
                )}
              >
                {selectionStatusLabel}
              </Badge>
              <Button
                onClick={handleBuild}
                disabled={isBuilding || (!selectionLocked && selectedSkills.size === 0)}
                size="lg"
                className="gap-2 shadow-sm"
              >
                {isBuilding ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {isBuilding
                  ? 'Building...'
                  : selectionLocked
                    ? 'Rebuild Learning Path'
                    : 'Build My Learning Path'}
              </Button>
            </div>
          </div>

          <p
            className={cn(
              'text-sm',
              selectionLocked || isSelectionCountInRange
                ? 'text-muted-foreground'
                : 'text-amber-900 dark:text-amber-100',
            )}
          >
            {selectionHelperText}
          </p>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <HeroStat
              icon={<Library className="h-4 w-4" />}
              label="Books in bank"
              value={`${totalBookCount}`}
              detail={`${totalBookChapterCount} chapters`}
              tone="book"
            />
            <HeroStat
              icon={<Briefcase className="h-4 w-4" />}
              label="Market postings"
              value={`${allMarketPostings.length}`}
              detail={`${totalMarketSkillCount} surfaced skills`}
              tone="market"
            />
            <HeroStat
              icon={<CheckCircle2 className="h-4 w-4" />}
              label="Selected skills"
              value={`${selectedSkills.size}`}
              detail={
                selectionLocked
                  ? 'Saved in your learning path'
                  : `${selectionRange.min_skills}-${selectionRange.max_skills} allowed before build`
              }
              tone="selected"
            />
            <HeroStat
              icon={<Search className="h-4 w-4" />}
              label="Interested postings"
              value={`${interestedPostings.size}`}
              detail={
                selectionLocked ? 'Saved from prior selections' : 'Pinned to the top while selecting'
              }
              tone="neutral"
            />
          </div>
        </div>
      </section>

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

      <PrerequisiteReviewDialog
        open={prerequisiteReviewOpen}
        onOpenChange={setPrerequisiteReviewOpen}
        items={unresolvedPrerequisiteItems}
        onAddToLearningPath={handleAddPrerequisiteToSelection}
        onAcknowledgeKnown={handleAcknowledgeKnownPrerequisite}
        onContinueBuild={() => void handleContinueBuildAfterPrerequisiteReview()}
      />

      {!selectionLocked ? (
        <section className="space-y-4">
          <Card className="border-border/60 bg-card/70 shadow-none">
            <CardContent className="flex flex-col gap-4 pt-6">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="relative w-full lg:max-w-xl">
                  <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Search books, chapters, skills, postings, or companies"
                    className="h-10 border-border/70 bg-background/80 pl-10"
                  />
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    variant={showSelectedOnly ? 'default' : 'outline'}
                    size="sm"
                    className="rounded-full"
                    onClick={() => setShowSelectedOnly((prev) => !prev)}
                  >
                    {showSelectedOnly ? 'Showing selected only' : 'Show selected only'}
                  </Button>
                  <Badge variant="outline" className="rounded-full">
                    {visibleBookSkillCount + visibleMarketSkillCount} visible skills
                  </Badge>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="gap-1">
                  <Library className="h-3 w-3" />
                  {filteredBookBanks.length} of {totalBookCount} books
                </Badge>
                <Badge variant="outline" className="gap-1">
                  <BookOpen className="h-3 w-3" />
                  {visibleBookChapterCount} visible chapters
                </Badge>
                <Badge variant="outline" className="gap-1">
                  <Briefcase className="h-3 w-3" />
                  {filteredMarketSkillBank.length} visible postings
                </Badge>
                <Badge variant="outline" className="gap-1">
                  <Users className="h-3 w-3" />
                  Peer badges show what classmates picked
                </Badge>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-4 xl:grid-cols-[1.2fr_1fr]">
            <Card className="border-border/60 shadow-none">
              <CardHeader className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <BookOpen className="h-4 w-4 text-blue-600" />
                      Book Skill Banks
                    </CardTitle>
                    <CardDescription>
                      Explore all course-linked books and drill down chapter by chapter.
                    </CardDescription>
                  </div>
                  <Badge variant="secondary">
                    {visibleBookSkillCount}
                    {visibleBookSkillCount !== totalBookSkillCount ? ` / ${totalBookSkillCount}` : ''} skills
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {filteredBookBanks.length > 0 ? (
                  filteredBookBanks.map((book) => (
                    <BookBankCard
                      key={book.book_id}
                      book={book}
                      selectedSkills={selectedSkills}
                      prerequisiteIndex={directPrerequisiteIndex}
                      onSkillClick={toggleSkill}
                    />
                  ))
                ) : (
                  <EmptySkillBank
                    icon={<Library className="h-6 w-6" />}
                    title="No books match this view"
                    description="Try a different search term or turn off the selected-only filter to explore the full book bank."
                  />
                )}
              </CardContent>
            </Card>

            <Card className="border-border/60 shadow-none">
              <CardHeader className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="space-y-1">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Briefcase className="h-4 w-4 text-emerald-600" />
                      Job-Posting Skill Bank
                    </CardTitle>
                    <CardDescription>
                      Keep market demand in context by reviewing skills inside the postings that surfaced them.
                    </CardDescription>
                  </div>
                  <Badge variant="secondary">
                    {visibleMarketSkillCount}
                    {visibleMarketSkillCount !== totalMarketSkillCount ? ` / ${totalMarketSkillCount}` : ''} skills
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {filteredMarketSkillBank.length > 0 ? (
                  <Accordion
                    type="multiple"
                    defaultValue={filteredMarketSkillBank.length > 0 ? [`job-${filteredMarketSkillBank[0]!.url}`] : []}
                  >
                    {filteredMarketSkillBank.map((posting) => {
                      const isInterested = interestedPostings.has(posting.url);

                      return (
                        <AccordionItem key={posting.url} value={`job-${posting.url}`}>
                          <AccordionTrigger className="gap-3 hover:no-underline">
                            <div className="flex min-w-0 flex-1 items-center gap-3 text-left">
                              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                                <Briefcase className="h-4 w-4" />
                              </div>
                              <div className="min-w-0 space-y-1">
                                <p className="truncate font-medium">{posting.title}</p>
                                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                                  {posting.company && (
                                    <span className="inline-flex items-center gap-1">
                                      <Building2 className="h-3 w-3" />
                                      {posting.company}
                                    </span>
                                  )}
                                  <span className="inline-flex items-center gap-1">
                                    <Globe className="h-3 w-3" />
                                    {posting.site || 'Job posting'}
                                  </span>
                                </div>
                              </div>
                            </div>

                            <div className="flex items-center gap-2">
                              <Badge variant={isInterested ? 'default' : 'secondary'} className="shrink-0">
                                {isInterested ? 'Interested' : 'Not interested'}
                              </Badge>
                              <Badge variant="outline" className="shrink-0">
                                {posting.skills.length} skills
                              </Badge>
                              <Button
                                type="button"
                                size="sm"
                                variant={isInterested ? 'default' : 'outline'}
                                className="gap-1.5"
                                onClick={(event) => {
                                  event.preventDefault();
                                  event.stopPropagation();
                                  toggleJobPosting(posting);
                                }}
                              >
                                <Sparkles className="h-3.5 w-3.5" />
                                {isInterested ? 'Saved' : 'Save'}
                              </Button>
                            </div>
                          </AccordionTrigger>
                          <AccordionContent>
                            <div className="space-y-3 pl-2 pt-1">
                              <a
                                href={posting.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
                              >
                                View job posting
                                <ExternalLink className="h-3 w-3" />
                              </a>

                              {posting.skills.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                  {posting.skills.map((skill) => (
                                    <SkillChip
                                      key={skill.name}
                                      skill={skill}
                                      isSelected={selectedSkills.has(skill.name)}
                                      peerCount={skill.peer_count ?? 0}
                                      directPrerequisites={directPrerequisiteIndex.get(skill.name) ?? []}
                                      onClick={() => toggleSkill(skill.name, 'market')}
                                    />
                                  ))}
                                </div>
                              ) : (
                                <p className="text-sm italic text-muted-foreground">
                                  No skills linked to this posting yet.
                                </p>
                              )}
                            </div>
                          </AccordionContent>
                        </AccordionItem>
                      );
                    })}
                  </Accordion>
                ) : (
                  <EmptySkillBank
                    icon={<Briefcase className="h-6 w-6" />}
                    title="No postings match this view"
                    description="Try a broader search or turn off the selected-only filter to browse the full market bank."
                  />
                )}
              </CardContent>
            </Card>
          </div>
        </section>
      ) : (
        <section className="space-y-4">
          {!learningPath || learningPath.chapters.length === 0 ? (
            <Card>
              <CardContent className="pt-6 text-center text-muted-foreground">
                <Sparkles className="mx-auto mb-3 h-10 w-10 text-muted-foreground/50" />
                <p>No learning path yet. Click &quot;Build My Learning Path&quot; to get started.</p>
              </CardContent>
            </Card>
          ) : (
            <Accordion
              type="multiple"
              defaultValue={learningPath.chapters.length > 0 ? ['ch-0'] : []}
            >
              {learningPath.chapters.map((chapter, chIdx) => (
                <AccordionItem key={chIdx} value={`ch-${chIdx}`}>
                  <AccordionTrigger className="text-lg font-semibold">
                    Chapter {chapter.chapter_index}: {chapter.title}
                    <Badge variant="outline" className="ml-2">
                      {chapter.selected_skills.length} skills
                    </Badge>
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
                            {skill.readings.length > 0 && (
                              <div>
                                <h4 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
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
                                      className="flex items-start gap-2 rounded-md border p-2 text-sm transition-colors hover:bg-accent"
                                    >
                                      <ExternalLink className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                                      <div className="min-w-0">
                                        <p className="truncate font-medium">{r.title}</p>
                                        <p className="truncate text-xs text-muted-foreground">{r.domain}</p>
                                      </div>
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}

                            {skill.videos.length > 0 && (
                              <div>
                                <h4 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
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
                                      className="flex items-start gap-2 rounded-md border p-2 text-sm transition-colors hover:bg-accent"
                                    >
                                      <Video className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                                      <div className="min-w-0">
                                        <p className="truncate font-medium">{v.title}</p>
                                        <p className="truncate text-xs text-muted-foreground">{v.domain}</p>
                                      </div>
                                    </a>
                                  ))}
                                </div>
                              </div>
                            )}

                            {skill.questions.length > 0 && (
                              <>
                                <Separator />
                                <div>
                                  <h4 className="mb-2 flex items-center gap-1.5 text-sm font-medium">
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

                            {skill.questions.length === 0 &&
                              (skill.readings.length > 0 || skill.videos.length > 0) && (
                                <>
                                  <Separator />
                                  <div className="rounded-md border border-amber-200/60 bg-amber-50/80 p-3 text-sm text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-100">
                                    Questions are not available yet. Try rebuilding the learning path.
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
        </section>
      )}
    </div>
  );
}

function HeroStat({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  tone: 'book' | 'market' | 'selected' | 'neutral';
}) {
  const toneStyles = {
    book: 'border-blue-500/20 bg-blue-500/10 text-blue-700 dark:text-blue-300',
    market: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    selected: 'border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300',
    neutral: 'border-border/60 bg-background/70 text-foreground',
  } as const;

  return (
    <div className="rounded-2xl border border-border/60 bg-background/70 p-4 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold tracking-tight">{value}</p>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
        <div className={cn('rounded-2xl border p-2', toneStyles[tone])}>{icon}</div>
      </div>
    </div>
  );
}

function BookBankCard({
  book,
  selectedSkills,
  prerequisiteIndex,
  onSkillClick,
}: {
  book: StudentSkillBankBook;
  selectedSkills: Set<string>;
  prerequisiteIndex: Map<string, PrerequisiteEdge[]>;
  onSkillClick: (skillName: string, source: 'book' | 'market') => void;
}) {
  const skillCount = book.chapters.reduce((total, chapter) => total + chapter.skills.length, 0);

  return (
    <Card className="overflow-hidden border-border/60 bg-muted/20 shadow-none">
      <CardHeader className="pb-3">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300">
            <Library className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <CardTitle className="text-sm">{book.title}</CardTitle>
              <Badge variant="secondary" className="text-[10px]">
                {book.chapters.length} chapters
              </Badge>
              <Badge variant="secondary" className="text-[10px]">
                {skillCount} skills
              </Badge>
            </div>
            {book.authors && (
              <CardDescription className="line-clamp-1 text-xs">{book.authors}</CardDescription>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <Accordion type="multiple" defaultValue={book.chapters.length > 0 ? [book.chapters[0]!.chapter_id] : []}>
          {book.chapters.map((chapter) => (
            <AccordionItem key={chapter.chapter_id} value={chapter.chapter_id}>
              <AccordionTrigger className="gap-3 py-3 hover:no-underline">
                <div className="flex min-w-0 flex-1 items-center gap-3 text-left">
                  <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-background text-xs font-semibold text-muted-foreground">
                    {chapter.chapter_index}
                  </div>
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      Chapter {chapter.chapter_index}: {chapter.title}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {chapter.skills.length} skill{chapter.skills.length === 1 ? '' : 's'}
                    </p>
                  </div>
                </div>
              </AccordionTrigger>
              <AccordionContent>
                {chapter.skills.length > 0 ? (
                  <div className="flex flex-wrap gap-2 pl-11 pt-1">
                    {chapter.skills.map((skill) => (
                      <SkillChip
                        key={`${chapter.chapter_id}-${skill.name}`}
                        skill={skill}
                        isSelected={selectedSkills.has(skill.name)}
                        peerCount={skill.peer_count ?? 0}
                        directPrerequisites={prerequisiteIndex.get(skill.name) ?? []}
                        onClick={() => onSkillClick(skill.name, 'book')}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="pl-11 text-sm italic text-muted-foreground">
                    No skills mapped to this chapter.
                  </p>
                )}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </CardContent>
    </Card>
  );
}

function SkillChip({
  skill,
  isSelected,
  peerCount,
  directPrerequisites,
  onClick,
}: {
  skill: StudentSkillBankSkill;
  isSelected: boolean;
  peerCount: number;
  directPrerequisites: PrerequisiteEdge[];
  onClick: () => void;
}) {
  const hasDirectPrerequisites = directPrerequisites.length > 0;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant={isSelected ? 'default' : 'outline'}
        size="sm"
        className="h-auto min-h-9 rounded-full px-3 py-1.5 transition-all"
        onClick={onClick}
        title={skill.description || ''}
      >
        {isSelected ? <CheckCircle2 className="h-3.5 w-3.5" /> : null}
        <span className="max-w-[16rem] truncate">{skill.name}</span>
        {peerCount > 0 && (
          <Badge
            variant={isSelected ? 'secondary' : 'default'}
            className="ml-1 rounded-full px-1.5 py-0 text-[10px] opacity-85"
          >
            <Users className="mr-0.5 h-3 w-3" />
            {peerCount}
          </Badge>
        )}
      </Button>

      {hasDirectPrerequisites && (
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" size="sm" variant="outline" className="h-8 rounded-full px-2.5 text-[11px]">
              Requires {directPrerequisites.length}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80">
            <PopoverHeader>
              <PopoverTitle>Direct prerequisites</PopoverTitle>
              <PopoverDescription>
                These skills are linked as foundations for {skill.name}.
              </PopoverDescription>
            </PopoverHeader>
            <div className="mt-3 space-y-3">
              {directPrerequisites.map((prerequisite) => (
                <div key={`${skill.name}-${prerequisite.prerequisite_name}`} className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{prerequisite.prerequisite_name}</p>
                    <Badge variant="outline" className="text-[10px]">
                      {formatPrerequisiteConfidence(prerequisite.confidence)}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {prerequisite.reasoning || 'Marked as a prerequisite in the course graph.'}
                  </p>
                </div>
              ))}
            </div>
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}

function EmptySkillBank({
  icon,
  title,
  description,
}: {
  icon: ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-14 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        {icon}
      </div>
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{description}</p>
    </div>
  );
}

function QuestionCard({ question }: { question: QuestionWithOptions }) {
  const [showAnswer, setShowAnswer] = useState(false);
  const difficultyColors: Record<string, string> = {
    easy: 'bg-green-500/10 text-green-700 dark:text-green-400',
    medium: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
    hard: 'bg-red-500/10 text-red-700 dark:text-red-400',
  };
  const optionLabels = ['A', 'B', 'C', 'D'];
  const hasOptions = Array.isArray(question.options) && question.options.length === 4;
  const options: string[] = hasOptions ? question.options ?? [] : [];

  return (
    <div className="space-y-2 rounded-md border p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm">{question.text}</p>
        <Badge className={`shrink-0 ${difficultyColors[question.difficulty] || ''}`}>
          {question.difficulty}
        </Badge>
      </div>
      {hasOptions && (
        <div className="grid gap-2">
          {options.map((option, index) => {
            const label = optionLabels[index] || String(index + 1);
            const isCorrect = label === question.correct_option;

            return (
              <div
                key={`${label}-${option}`}
                className={`rounded-md border px-3 py-2 text-sm transition-colors ${
                  showAnswer
                    ? isCorrect
                      ? 'border-green-500/40 bg-green-500/10 text-green-800 dark:text-green-300'
                      : 'bg-background'
                    : 'bg-background'
                }`}
              >
                <span className="mr-2 font-medium">{label}.</span>
                <span>{option}</span>
              </div>
            );
          })}
        </div>
      )}
      <Button variant="ghost" size="sm" onClick={() => setShowAnswer(!showAnswer)}>
        {showAnswer ? 'Hide Answer' : 'Show Answer'}
      </Button>
      {showAnswer && (
        <div className="animate-in space-y-1 rounded-md bg-muted p-2 text-sm text-muted-foreground fade-in-0 slide-in-from-top-1">
          {question.correct_option && (
            <p>
              <span className="font-medium text-foreground">Correct answer:</span>{' '}
              {question.correct_option}
            </p>
          )}
          <p>{question.answer}</p>
        </div>
      )}
    </div>
  );
}

function formatPrerequisiteConfidence(confidence: 'high' | 'medium' | 'low') {
  return `${confidence[0]!.toUpperCase()}${confidence.slice(1)} confidence`;
}

function buildPrerequisiteIndex(edges: PrerequisiteEdge[]) {
  return edges.reduce<Map<string, PrerequisiteEdge[]>>((index, edge) => {
    const existing = index.get(edge.dependent_name) ?? [];
    existing.push(edge);
    index.set(edge.dependent_name, existing);
    return index;
  }, new Map());
}

function collectTransitivePrerequisites(
  selectedSkills: Set<string>,
  prerequisiteIndex: Map<string, PrerequisiteEdge[]>,
) {
  const visited = new Set<string>();
  const queue = Array.from(selectedSkills);

  while (queue.length > 0) {
    const skillName = queue.shift();
    if (!skillName) {
      continue;
    }
    for (const edge of prerequisiteIndex.get(skillName) ?? []) {
      if (visited.has(edge.prerequisite_name)) {
        continue;
      }
      visited.add(edge.prerequisite_name);
      queue.push(edge.prerequisite_name);
    }
  }

  return visited;
}

function buildPrerequisiteReviewItems(
  selectedSkills: Set<string>,
  acknowledgedKnownSkills: Set<string>,
  prerequisiteIndex: Map<string, PrerequisiteEdge[]>,
): PrerequisiteReviewItem[] {
  const itemMap = new Map<string, PrerequisiteReviewItem>();
  const queue = Array.from(selectedSkills);
  const visitedDependents = new Set<string>();

  while (queue.length > 0) {
    const skillName = queue.shift();
    if (!skillName || visitedDependents.has(skillName)) {
      continue;
    }
    visitedDependents.add(skillName);

    for (const edge of prerequisiteIndex.get(skillName) ?? []) {
      if (!selectedSkills.has(edge.prerequisite_name) && !acknowledgedKnownSkills.has(edge.prerequisite_name)) {
        const existing = itemMap.get(edge.prerequisite_name);
        if (existing) {
          if (!existing.dependentSkillNames.includes(skillName)) {
            existing.dependentSkillNames.push(skillName);
          }
          if (!existing.reasoning && edge.reasoning) {
            existing.reasoning = edge.reasoning;
          }
        } else {
          itemMap.set(edge.prerequisite_name, {
            name: edge.prerequisite_name,
            dependentSkillNames: [skillName],
            reasoning: edge.reasoning,
            confidence: edge.confidence,
          });
        }
      }
      queue.push(edge.prerequisite_name);
    }
  }

  return Array.from(itemMap.values()).sort((left, right) => left.name.localeCompare(right.name));
}

function inferPrerequisiteSource(
  skillName: string,
  skillBanks: SkillBanksResponse | null,
): 'book' | 'market' {
  const isBookSkill = skillBanks?.book_skill_banks.some((book) =>
    book.chapters.some((chapter) => chapter.skills.some((skill) => skill.name === skillName)),
  );
  return isBookSkill ? 'book' : 'market';
}

type QuestionWithOptions = {
  text: string;
  difficulty: string;
  answer: string;
  options?: string[];
  correct_option?: 'A' | 'B' | 'C' | 'D' | null;
};

function matchesSearch(query: string, ...values: Array<string | null | undefined>): boolean {
  if (!query) {
    return false;
  }

  return values.some((value) => value?.toLowerCase().includes(query));
}

function filterBookSkillBanks(
  books: StudentSkillBankBook[],
  query: string,
  showSelectedOnly: boolean,
  selectedSkills: Set<string>,
): StudentSkillBankBook[] {
  const hasQuery = query.length > 0;

  return books.flatMap((book) => {
    const bookMatches = hasQuery && matchesSearch(query, book.title, book.authors);

    const chapters = book.chapters.flatMap((chapter) => {
      const chapterMatches =
        bookMatches ||
        (hasQuery && matchesSearch(query, chapter.title, `chapter ${chapter.chapter_index}`));

      const skills = chapter.skills.filter((skill) => {
        const isSelected = selectedSkills.has(skill.name);
        if (showSelectedOnly && !isSelected) {
          return false;
        }
        if (!hasQuery || chapterMatches) {
          return true;
        }
        return matchesSearch(query, skill.name, skill.description);
      });

      if (!chapterMatches && skills.length === 0) {
        return [];
      }

      return [{ ...chapter, skills }];
    });

    if (!bookMatches && chapters.length === 0) {
      return [];
    }

    return [{ ...book, chapters }];
  });
}

function filterMarketSkillBank(
  postings: StudentSkillBankJobPosting[],
  query: string,
  showSelectedOnly: boolean,
  selectedSkills: Set<string>,
  interestedPostings: Set<string>,
): StudentSkillBankJobPosting[] {
  const hasQuery = query.length > 0;

  return postings
    .flatMap((posting) => {
      const postingMatches =
        hasQuery &&
        matchesSearch(query, posting.title, posting.company, posting.site, posting.search_term);

      const skills = posting.skills.filter((skill) => {
        const isSelected = selectedSkills.has(skill.name);
        if (showSelectedOnly && !isSelected) {
          return false;
        }
        if (!hasQuery || postingMatches) {
          return true;
        }
        return matchesSearch(query, skill.name, skill.description, skill.category);
      });

      if (!postingMatches && skills.length === 0) {
        return [];
      }

      return [{ ...posting, skills }];
    })
    .sort((left, right) => {
      const leftInterested = interestedPostings.has(left.url);
      const rightInterested = interestedPostings.has(right.url);
      if (leftInterested !== rightInterested) {
        return leftInterested ? -1 : 1;
      }
      return left.title.localeCompare(right.title);
    });
}
