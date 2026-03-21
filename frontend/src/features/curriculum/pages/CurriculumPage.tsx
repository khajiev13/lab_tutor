import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  BookText,
  Loader2,
  PanelRightClose,
  PanelRightOpen,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

import { coursesApi } from "@/features/courses/api";

import type { CurriculumWithChangelog } from "../types";

import { ChapterAccordion } from "../components/ChapterAccordion";
import { ChangelogTimeline } from "../components/ChangelogTimeline";
import { CurriculumStats } from "../components/CurriculumStats";

export default function CurriculumPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const courseId = useMemo(() => Number(id), [id]);

  // Curriculum tree state
  const [data, setData] = useState<CurriculumWithChangelog | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);



  // Panel state
  const [panelOpen, setPanelOpen] = useState(true);

  // Load curriculum tree
  const loadCurriculum = useCallback(async () => {
    if (!Number.isFinite(courseId)) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await coursesApi.getCurriculum(courseId);
      setData(result);
    } catch {
      setError(
        "Failed to load curriculum. Ensure the course has a linked book and Neo4j is available."
      );
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    loadCurriculum();
  }, [loadCurriculum]);



  if (!Number.isFinite(courseId)) {
    return (
      <Alert variant="destructive">
        <AlertTitle>Invalid course</AlertTitle>
        <AlertDescription>Missing or invalid course id.</AlertDescription>
      </Alert>
    );
  }

  const curriculum = data?.curriculum;
  const isEmpty = curriculum && curriculum.chapters.length === 0;

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 shrink-0">
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
                <Link to={`/courses/${courseId}`}>
                  {curriculum?.book_title ?? "Course"}
                </Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbPage>Curriculum</BreadcrumbPage>
            </BreadcrumbItem>
          </BreadcrumbList>
        </Breadcrumb>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={loadCurriculum} disabled={isLoading}>
            Refresh
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setPanelOpen(!panelOpen)}
            className="text-muted-foreground"
          >
            {panelOpen ? (
              <PanelRightClose className="size-4" />
            ) : (
              <PanelRightOpen className="size-4" />
            )}
          </Button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <Alert variant="destructive" className="mb-4 shrink-0">
          <AlertTitle>Error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" />
          Loading curriculum…
        </div>
      )}

      {/* Empty state */}
      {!isLoading && isEmpty && (
        <Empty className="py-20">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <BookText />
            </EmptyMedia>
            <EmptyTitle>No curriculum built yet</EmptyTitle>
            <EmptyDescription>
              Use the Curricular Alignment Architect to select and analyze a
              textbook, then build the curriculum graph.
            </EmptyDescription>
          </EmptyHeader>
          <Button
            variant="secondary"
            onClick={() => navigate(`/courses/${courseId}/architect`)}
          >
            Go to Architect
          </Button>
        </Empty>
      )}

      {/* Main content */}
      {!isLoading && curriculum && curriculum.chapters.length > 0 && (
        <div className="flex flex-1 min-h-0 gap-0">
          {/* Main column */}
          <div className="flex-1 min-w-0 overflow-y-auto pr-2">
            {/* Book info header */}
            {curriculum.book_title && (
              <div className="mb-4">
                <h2 className="text-lg font-semibold">{curriculum.book_title}</h2>
                {curriculum.book_authors && (
                  <p className="text-sm text-muted-foreground">
                    {curriculum.book_authors}
                  </p>
                )}
              </div>
            )}

            {/* Stats */}
            <div className="mb-5">
              <CurriculumStats curriculum={curriculum} />
            </div>

            {/* Curriculum Tree */}
            <div className="mt-4">
              <ChapterAccordion chapters={curriculum.chapters} />
            </div>
          </div>

          {/* Timeline sidebar */}
          {panelOpen && (
            <div className="w-72 xl:w-80 shrink-0 hidden md:flex flex-col border-l h-full">
              <div className="px-4 py-3 border-b shrink-0">
                <h3 className="text-sm font-semibold">Agent Changelog</h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Track how agents modified the curriculum
                </p>
              </div>
              <div className="flex-1 min-h-0">
                <ChangelogTimeline changelog={data?.changelog ?? []} />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
