import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  BookOpen,
  BookText,
  FileText,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
  TrendingUp,
} from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { coursesApi } from '@/features/courses/api';
import type { Course } from '@/features/courses/types';
import { BookSkillBank } from '@/features/curriculum/components/BookSkillBank';
import { CurriculumStats } from '@/features/curriculum/components/CurriculumStats';
import { MarketSkillBank } from '@/features/curriculum/components/MarketSkillBank';
import { SkillSelectionRangeCard } from '@/features/curriculum/components/SkillSelectionRangeCard';
import { StudentActivityOverviewCard } from '@/features/curriculum/components/StudentActivityOverviewCard';
import { StudentInsightSidebarCard } from '@/features/curriculum/components/StudentInsightSidebarCard';
import { TranscriptChapters } from '@/features/curriculum/components/TranscriptChapters';
import {
  adaptTeacherBookSkillBanks,
  adaptTeacherBookSkillBanksWithOverlay,
  adaptTeacherMarketSkillBank,
  adaptTeacherMarketSkillBankWithOverlay,
} from '@/features/curriculum/skill-bank-display';
import type {
  SkillBanksResponse,
  StudentInsightsOverview,
  TeacherStudentInsightDetail,
} from '@/features/curriculum/types';

function SectionAlert({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <Alert className="border-border/60 bg-muted/20">
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{description}</AlertDescription>
    </Alert>
  );
}

function countBookSkills<
  TBook extends { chapters: Array<{ skills: Array<unknown> }> },
>(books: TBook[]) {
  return books.reduce(
    (total, book) =>
      total + book.chapters.reduce((chapterTotal, chapter) => chapterTotal + chapter.skills.length, 0),
    0,
  );
}

function countUniqueMarketSkills<
  TPosting extends { skills: Array<{ name: string }> },
>(jobPostings: TPosting[]) {
  return new Set(jobPostings.flatMap((posting) => posting.skills.map((skill) => skill.name))).size;
}

export default function CurriculumPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const courseId = useMemo(() => Number(id), [id]);
  const invalidCourse = !Number.isFinite(courseId);

  const [course, setCourse] = useState<Course | null>(null);
  const [courseLoading, setCourseLoading] = useState(true);
  const [courseError, setCourseError] = useState<string | null>(null);

  const [skillBanks, setSkillBanks] = useState<SkillBanksResponse | null>(null);
  const [skillBanksLoading, setSkillBanksLoading] = useState(true);
  const [skillBanksError, setSkillBanksError] = useState<string | null>(null);

  const [studentInsights, setStudentInsights] = useState<StudentInsightsOverview | null>(null);
  const [studentInsightsLoading, setStudentInsightsLoading] = useState(true);
  const [studentInsightsError, setStudentInsightsError] = useState<string | null>(null);

  const [selectedStudentId, setSelectedStudentId] = useState<string | null>(null);
  const [selectedStudentDetail, setSelectedStudentDetail] = useState<TeacherStudentInsightDetail | null>(
    null,
  );
  const [studentDetailLoading, setStudentDetailLoading] = useState(false);
  const [studentDetailError, setStudentDetailError] = useState<string | null>(null);

  const [panelOpen, setPanelOpen] = useState(true);

  const loadCourseSection = useCallback(async () => {
    if (!Number.isFinite(courseId)) {
      return;
    }

    setCourseLoading(true);
    setCourseError(null);
    try {
      const result = await coursesApi.getCourse(courseId);
      setCourse(result);
    } catch {
      setCourse(null);
      setCourseError(
        'We could not load the course title right now. The curriculum workspace can still load below.',
      );
    } finally {
      setCourseLoading(false);
    }
  }, [courseId]);

  const loadSkillBanksSection = useCallback(async () => {
    if (!Number.isFinite(courseId)) {
      return;
    }

    setSkillBanksLoading(true);
    setSkillBanksError(null);
    try {
      const result = await coursesApi.getSkillBanks(courseId);
      setSkillBanks(result);
    } catch {
      setSkillBanks(null);
      setSkillBanksError(
        'The teacher skill banks are unavailable right now. You can still inspect student activity if that section loads.',
      );
    } finally {
      setSkillBanksLoading(false);
    }
  }, [courseId]);

  const loadStudentInsightsSection = useCallback(async () => {
    if (!Number.isFinite(courseId)) {
      return;
    }

    setStudentInsightsLoading(true);
    setStudentInsightsError(null);
    try {
      const result = await coursesApi.getStudentInsights(courseId);
      setStudentInsights(result);
      setSelectedStudentId((currentValue) => {
        if (currentValue && result.students.some((student) => String(student.id) === currentValue)) {
          return currentValue;
        }
        const firstActiveStudent = result.students.find(
          (student) => student.selected_skill_count > 0 || student.has_learning_path,
        );
        return firstActiveStudent ? String(firstActiveStudent.id) : null;
      });
    } catch {
      setStudentInsights(null);
      setSelectedStudentId(null);
      setSelectedStudentDetail(null);
      setStudentInsightsError(
        'Student insights are temporarily unavailable. The rest of the curriculum page can still load.',
      );
    } finally {
      setStudentInsightsLoading(false);
    }
  }, [courseId]);

  const loadStudentDetailSection = useCallback(
    async (studentId: string) => {
      if (!Number.isFinite(courseId)) {
        return;
      }

      setStudentDetailLoading(true);
      setStudentDetailError(null);
      try {
        const result = await coursesApi.getStudentInsightDetail(courseId, Number(studentId));
        setSelectedStudentDetail(result);
      } catch {
        setSelectedStudentDetail(null);
        setStudentDetailError(
          'We could not load this student’s saved learning-path detail. Try another student or refresh.',
        );
      } finally {
        setStudentDetailLoading(false);
      }
    },
    [courseId],
  );

  const refreshAllSections = useCallback(() => {
    void loadCourseSection();
    void loadSkillBanksSection();
    void loadStudentInsightsSection();
    if (selectedStudentId) {
      void loadStudentDetailSection(selectedStudentId);
    }
  }, [
    loadCourseSection,
    loadSkillBanksSection,
    loadStudentDetailSection,
    loadStudentInsightsSection,
    selectedStudentId,
  ]);

  useEffect(() => {
    void loadCourseSection();
    void loadSkillBanksSection();
    void loadStudentInsightsSection();
  }, [loadCourseSection, loadSkillBanksSection, loadStudentInsightsSection]);

  useEffect(() => {
    if (!selectedStudentId) {
      setSelectedStudentDetail(null);
      setStudentDetailError(null);
      return;
    }

    void loadStudentDetailSection(selectedStudentId);
  }, [loadStudentDetailSection, selectedStudentId]);

  const hasTranscripts = (skillBanks?.course_chapters.length ?? 0) > 0;
  const hasBookSkills = (skillBanks?.book_skill_bank.length ?? 0) > 0;
  const hasMarketSkills = (skillBanks?.market_skill_bank.length ?? 0) > 0;
  const hasCoreTeacherData = hasTranscripts || hasBookSkills || hasMarketSkills;
  const showFullPageEmptyState =
    !skillBanksLoading && !skillBanksError && !hasCoreTeacherData;

  const selectedStudentName = selectedStudentDetail?.student.full_name ?? null;
  const courseTitle = course?.title ?? 'Course';

  const displayBookBanks = useMemo(() => {
    if (selectedStudentDetail) {
      return adaptTeacherBookSkillBanksWithOverlay(
        skillBanks?.book_skill_bank ?? [],
        selectedStudentDetail,
      );
    }
    return adaptTeacherBookSkillBanks(skillBanks?.book_skill_bank ?? []);
  }, [selectedStudentDetail, skillBanks?.book_skill_bank]);

  const displayMarketSkillBank = useMemo(() => {
    if (selectedStudentDetail) {
      return adaptTeacherMarketSkillBankWithOverlay(
        skillBanks?.market_skill_bank ?? [],
        selectedStudentDetail,
      );
    }
    return adaptTeacherMarketSkillBank(skillBanks?.market_skill_bank ?? []);
  }, [selectedStudentDetail, skillBanks?.market_skill_bank]);

  const courseChapterCount = skillBanks?.course_chapters.length ?? 0;
  const transcriptFileCount =
    skillBanks?.course_chapters.reduce((sum, chapter) => sum + chapter.documents.length, 0) ?? 0;
  const displayBookSkillCount = countBookSkills(displayBookBanks);
  const displayMarketSkillCount = countUniqueMarketSkills(displayMarketSkillBank);
  const displayJobPostingCount = displayMarketSkillBank.length;

  const showTopLevelLoadingState =
    courseLoading &&
    skillBanksLoading &&
    studentInsightsLoading &&
    !course &&
    !skillBanks &&
    !studentInsights;

  if (invalidCourse) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Invalid course</AlertTitle>
        <AlertDescription>Missing or invalid course id.</AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-4 flex shrink-0 items-center justify-between">
        <Breadcrumb>
          <BreadcrumbList>
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to="/courses">Courses</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to={`/courses/${courseId}`}>{courseTitle}</Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Curriculum</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={refreshAllSections}>
            Refresh
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPanelOpen((currentValue) => !currentValue)}
            className="text-muted-foreground"
            aria-label={panelOpen ? 'Close panel' : 'Open panel'}
          >
            {panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>
      </div>

      {showTopLevelLoadingState && (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading curriculum workspace…
        </div>
      )}

      {!showTopLevelLoadingState && courseError && (
        <div className="mb-4">
          <SectionAlert title="Course details unavailable" description={courseError} />
        </div>
      )}

      {!showTopLevelLoadingState && studentInsightsLoading && !studentInsights && (
        <Alert className="mb-4 border-border/60 bg-muted/20">
          <Loader2 className="h-4 w-4 animate-spin" />
          <AlertTitle>Loading student activity</AlertTitle>
          <AlertDescription>Pulling saved student signals into the curriculum view.</AlertDescription>
        </Alert>
      )}

      {!showTopLevelLoadingState && studentInsightsError && (
        <div className="mb-4">
          <SectionAlert title="Student activity unavailable" description={studentInsightsError} />
        </div>
      )}

      {!showTopLevelLoadingState && studentInsights && (
        <StudentActivityOverviewCard overview={studentInsights} />
      )}

      {showFullPageEmptyState && (
        <Empty className="py-20">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BookText />
            </EmptyMedia>
            <EmptyTitle>No course chapters built yet</EmptyTitle>
            <EmptyDescription>
              Use the Curricular Alignment Architect to organize your course materials into chapters,
              then return here to review the aligned skill banks.
            </EmptyDescription>
          </EmptyHeader>
          <Button variant="secondary" onClick={() => navigate(`/courses/${courseId}/architect`)}>
            Go to Architect
          </Button>
        </Empty>
      )}

      {!showTopLevelLoadingState && !showFullPageEmptyState && (
        <div className="flex flex-1 min-h-0 gap-0">
          <div className="min-w-0 flex-1 overflow-y-auto pr-2">
            <div className="mb-4">
              <h1 className="text-2xl font-semibold tracking-tight">{course?.title ?? 'Course Curriculum'}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Review transcript chapters, supporting skill banks, and student activity in one
                workspace.
              </p>
            </div>

            {skillBanks && (
              <div className="mb-5">
                <CurriculumStats
                  courseChapterCount={courseChapterCount}
                  transcriptFileCount={transcriptFileCount}
                  bookSkillCount={displayBookSkillCount}
                  marketSkillCount={displayMarketSkillCount}
                  jobPostingCount={displayJobPostingCount}
                />
              </div>
            )}

            {skillBanks && (
              <SkillSelectionRangeCard
                courseId={courseId}
                selectionRange={skillBanks.selection_range}
                onUpdated={(selectionRange) =>
                  setSkillBanks((currentValue) =>
                    currentValue ? { ...currentValue, selection_range: selectionRange } : currentValue,
                  )
                }
              />
            )}

            {!skillBanks && skillBanksLoading && (
              <Alert className="mb-5 border-border/60 bg-muted/20">
                <Loader2 className="h-4 w-4 animate-spin" />
                <AlertTitle>Loading skill banks</AlertTitle>
                <AlertDescription>
                  Pulling transcript chapters, book skills, and market skills into the teacher
                  workspace.
                </AlertDescription>
              </Alert>
            )}

            <Tabs defaultValue="transcripts" className="mt-2">
              <TabsList className="mb-4">
                <TabsTrigger value="transcripts" className="gap-1.5">
                  <FileText className="size-3.5" />
                  Transcripts
                  {hasTranscripts && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px]">
                      {skillBanks?.course_chapters.length}
                    </span>
                  )}
                </TabsTrigger>
                <TabsTrigger value="book-skills" className="gap-1.5">
                  <BookOpen className="size-3.5" />
                  Book Skills
                  {displayBookSkillCount > 0 && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px]">{displayBookSkillCount}</span>
                  )}
                </TabsTrigger>
                <TabsTrigger value="market-skills" className="gap-1.5">
                  <TrendingUp className="size-3.5" />
                  Market Skills
                  {displayMarketSkillCount > 0 && (
                    <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px]">{displayMarketSkillCount}</span>
                  )}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="transcripts" className="space-y-4">
                {skillBanksError ? (
                  <SectionAlert title="Transcript bank unavailable" description={skillBanksError} />
                ) : (
                  <TranscriptChapters chapters={skillBanks?.course_chapters ?? []} />
                )}
              </TabsContent>

              <TabsContent value="book-skills" className="space-y-4">
                {skillBanksError && !selectedStudentDetail ? (
                  <SectionAlert title="Book skill bank unavailable" description={skillBanksError} />
                ) : (
                  <BookSkillBank books={displayBookBanks} selectedStudentName={selectedStudentName} />
                )}
              </TabsContent>

              <TabsContent value="market-skills" className="space-y-4">
                {skillBanksError && !selectedStudentDetail ? (
                  <SectionAlert title="Market skill bank unavailable" description={skillBanksError} />
                ) : (
                  <MarketSkillBank
                    jobPostings={displayMarketSkillBank}
                    selectedStudentName={selectedStudentName}
                  />
                )}
              </TabsContent>
            </Tabs>
          </div>

          {panelOpen && studentInsights && (
            <div className="hidden h-full w-72 shrink-0 border-l p-4 md:block xl:w-80">
              <StudentInsightSidebarCard
                overview={studentInsights}
                selectedStudentId={selectedStudentId}
                onSelectStudent={setSelectedStudentId}
                detail={selectedStudentDetail}
                isLoadingDetail={studentDetailLoading}
              />
              {studentDetailError && (
                <div className="mt-3">
                  <SectionAlert title="Student overlay unavailable" description={studentDetailError} />
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
