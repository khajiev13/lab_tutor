import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  BookText,
  Loader2,
  Network,
  PanelRightClose,
  PanelRightOpen,
  TreePine,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { GraphViewer } from "@/features/graph/components/GraphViewer";
import type { CourseGraphResponse, GraphNode } from "@/features/graph/types";
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

  // Graph tab state
  const [graph, setGraph] = useState<CourseGraphResponse | null>(null);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [isExpanding, setIsExpanding] = useState(false);

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

  // Lazy-load graph data when Graph tab is selected
  const loadGraph = useCallback(async () => {
    if (graphLoaded || !Number.isFinite(courseId)) return;
    setIsLoadingGraph(true);
    try {
      const result = await coursesApi.getCourseGraph(courseId, {
        max_documents: 120,
        max_concepts: 900,
      });
      setGraph(result);
      setGraphLoaded(true);
    } catch {
      toast.error("Failed to load knowledge graph");
    } finally {
      setIsLoadingGraph(false);
    }
  }, [courseId, graphLoaded]);

  const mergeGraph = useCallback(
    (prev: CourseGraphResponse, delta: CourseGraphResponse) => {
      const nodesById = new Map(prev.nodes.map((n) => [n.id, n] as const));
      const edgesById = new Map(prev.edges.map((e) => [e.id, e] as const));
      for (const n of delta.nodes) nodesById.set(n.id, n);
      for (const e of delta.edges) edgesById.set(e.id, e);
      return {
        nodes: Array.from(nodesById.values()),
        edges: Array.from(edgesById.values()),
      };
    },
    []
  );

  const handleExpand = useCallback(
    async (node: GraphNode) => {
      if (!Number.isFinite(courseId)) return;
      setIsExpanding(true);
      try {
        const key =
          node.kind === "document" && "document_id" in node.data
            ? String(node.data.document_id)
            : node.kind === "concept" && "name" in node.data
              ? String(node.data.name)
              : "";
        const delta = await coursesApi.expandCourseGraph(courseId, {
          node_kind: node.kind,
          node_key: key,
          limit: 250,
          max_concepts: 900,
        });
        setGraph((prev) => (prev ? mergeGraph(prev, delta) : delta));
      } catch {
        toast.error("Failed to expand graph");
      } finally {
        setIsExpanding(false);
      }
    },
    [courseId, mergeGraph]
  );

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

            {/* Tabs: Tree / Graph */}
            <Tabs
              defaultValue="tree"
              onValueChange={(v) => {
                if (v === "graph") loadGraph();
              }}
            >
              <TabsList>
                <TabsTrigger value="tree">
                  <TreePine className="size-4 mr-1.5" />
                  Curriculum Tree
                </TabsTrigger>
                <TabsTrigger value="graph">
                  <Network className="size-4 mr-1.5" />
                  Knowledge Graph
                </TabsTrigger>
              </TabsList>

              <TabsContent value="tree" className="mt-4">
                <ChapterAccordion chapters={curriculum.chapters} />
              </TabsContent>

              <TabsContent value="graph" className="mt-4">
                {isLoadingGraph && (
                  <div className="flex items-center justify-center py-16 text-muted-foreground">
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    Loading graph…
                  </div>
                )}
                {isExpanding && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Expanding…
                  </div>
                )}
                {graph && <GraphViewer graph={graph} onExpand={handleExpand} />}
              </TabsContent>
            </Tabs>
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
