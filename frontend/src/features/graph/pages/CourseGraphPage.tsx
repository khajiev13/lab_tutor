import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { coursesApi } from '@/features/courses/api';
import type { CourseGraphResponse, GraphNode } from '../types';
import { GraphViewer } from '../components/GraphViewer';

export default function CourseGraphPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const courseId = useMemo(() => Number(id), [id]);

  const [graph, setGraph] = useState<CourseGraphResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isExpanding, setIsExpanding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(courseId)) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await coursesApi.getCourseGraph(courseId, { max_documents: 120, max_concepts: 900 });
      setGraph(data);
    } catch (e) {
      setError('Failed to load the course graph. Ensure Neo4j is enabled and try again.');
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    load();
  }, [load]);

  const mergeGraph = useCallback((prev: CourseGraphResponse, delta: CourseGraphResponse) => {
    const nodesById = new Map(prev.nodes.map((n) => [n.id, n] as const));
    const edgesById = new Map(prev.edges.map((e) => [e.id, e] as const));
    for (const n of delta.nodes) nodesById.set(n.id, n);
    for (const e of delta.edges) edgesById.set(e.id, e);
    return { nodes: Array.from(nodesById.values()), edges: Array.from(edgesById.values()) };
  }, []);

  const handleExpand = useCallback(
    async (node: GraphNode) => {
      if (!Number.isFinite(courseId)) return;
      setIsExpanding(true);
      try {
        const key =
          node.kind === 'document' && 'document_id' in node.data
            ? String(node.data.document_id)
            : node.kind === 'concept' && 'name' in node.data
              ? String(node.data.name)
              : '';

        const delta = await coursesApi.expandCourseGraph(courseId, {
          node_kind: node.kind,
          node_key: key,
          limit: 250,
          max_concepts: 900,
        });
        setGraph((prev) => (prev ? mergeGraph(prev, delta) : delta));
      } catch (e) {
        toast.error('Failed to expand graph');
        console.error(e);
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          className="pl-0 hover:bg-transparent hover:text-primary"
          onClick={() => navigate(`/courses/${courseId}`)}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Course
        </Button>
        <div className="flex items-center gap-2">
          <Button type="button" variant="secondary" onClick={load} disabled={isLoading || isExpanding}>
            Refresh
          </Button>
          {isExpanding ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Expanding…
            </div>
          ) : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge graph</CardTitle>
          <CardDescription>
            Explore extracted concepts and their source documents. Select a node to see details; use Expand to load more.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert variant="destructive">
              <AlertTitle>Could not load graph</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {isLoading ? (
            <div className="flex items-center justify-center py-16 text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              Loading…
            </div>
          ) : graph ? (
            <GraphViewer graph={graph} onExpand={handleExpand} />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}





