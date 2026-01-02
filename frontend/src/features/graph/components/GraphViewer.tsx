import { useEffect, useMemo, useState } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type ReactFlowInstance,
  type Edge as RFEdge,
  type Node as RFNode,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';

import type { CourseGraphResponse, GraphEdge, GraphNode, GraphNodeKind } from '../types';

type Props = {
  graph: CourseGraphResponse;
  onExpand: (node: GraphNode) => Promise<void>;
};

type LayoutMode = 'compact' | 'scatter';

function getKindBadgeVariant(kind: GraphNodeKind): 'default' | 'secondary' | 'outline' {
  if (kind === 'concept') return 'secondary';
  if (kind === 'document') return 'outline';
  return 'default';
}

function hashStringToInt(s: string) {
  // Deterministic small hash (no crypto) for stable scatter positions.
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function stableLayout(nodes: GraphNode[], edges: GraphEdge[], layoutMode: LayoutMode) {
  const classNodes = nodes.filter((n) => n.kind === 'class');
  const documentNodes = nodes.filter((n) => n.kind === 'document');
  const conceptNodes = nodes.filter((n) => n.kind === 'concept');

  // Stable, deterministic columns: CLASS -> DOCUMENT -> CONCEPT
  const positions = new Map<string, { x: number; y: number }>();

  classNodes.forEach((n, idx) => {
    positions.set(n.id, { x: 0, y: idx * 120 });
  });

  documentNodes.forEach((n, idx) => {
    positions.set(n.id, { x: 320, y: idx * 90 });
  });

  // Try to cluster concepts by their first connected document for a slightly nicer layout.
  const docToConcepts = new Map<string, string[]>();
  for (const e of edges) {
    if (e.kind !== 'mentions') continue;
    if (!docToConcepts.has(e.source)) docToConcepts.set(e.source, []);
    docToConcepts.get(e.source)!.push(e.target);
  }

  const conceptOrder: string[] = [];
  for (const docId of documentNodes.map((d) => d.id)) {
    const cs = docToConcepts.get(docId) ?? [];
    for (const cid of cs) {
      if (!conceptOrder.includes(cid)) conceptOrder.push(cid);
    }
  }
  for (const c of conceptNodes.map((c) => c.id)) {
    if (!conceptOrder.includes(c)) conceptOrder.push(c);
  }

  // Concepts: keep them compact — multi-column grid or deterministic scatter.
  const baseX = 720;
  const baseY = 0;
  const count = conceptOrder.length;
  const columns = Math.max(2, Math.ceil(Math.sqrt(count)));
  const dx = 200;
  const dy = 64;

  conceptOrder.forEach((id, idx) => {
    if (layoutMode === 'scatter') {
      const h = hashStringToInt(id);
      const col = h % columns;
      const row = Math.floor(h / columns) % Math.max(1, Math.ceil(count / columns));
      const jitterX = (h % 13) - 6;
      const jitterY = ((h >> 8) % 11) - 5;
      positions.set(id, { x: baseX + col * dx + jitterX, y: baseY + row * dy + jitterY });
      return;
    }

    const col = idx % columns;
    const row = Math.floor(idx / columns);
    positions.set(id, { x: baseX + col * dx, y: baseY + row * dy });
  });

  return positions;
}

function toReactFlow(graph: CourseGraphResponse, layoutMode: LayoutMode) {
  const pos = stableLayout(graph.nodes, graph.edges, layoutMode);

  const rfNodes: RFNode[] = graph.nodes.map((n) => ({
    id: n.id,
    position: pos.get(n.id) ?? { x: 0, y: 0 },
    data: { label: n.label, kind: n.kind },
    type: 'default',
  }));

  const rfEdges: RFEdge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    animated: e.kind === 'mentions',
  }));

  return { rfNodes, rfEdges };
}

function summarizeNode(node: GraphNode, graph: CourseGraphResponse) {
  if (node.kind !== 'concept') {
    return { definitions: [], evidence: [] as string[], byDocument: [] as Array<{
      documentId: string;
      documentLabel: string;
      definitions: string[];
      evidence: string[];
    }> };
  }

  const nodeLabelById = new Map(graph.nodes.map((n) => [n.id, n.label] as const));

  const definitions = new Set<string>();
  const evidence = new Set<string>();

  const perDoc = new Map<
    string,
    { definitions: Set<string>; evidence: Set<string> }
  >();

  for (const e of graph.edges) {
    if (e.kind !== 'mentions') continue;
    if (e.target !== node.id) continue;

    if (!perDoc.has(e.source)) {
      perDoc.set(e.source, { definitions: new Set<string>(), evidence: new Set<string>() });
    }
    const bucket = perDoc.get(e.source)!;

    if (e.data?.definition) {
      definitions.add(e.data.definition);
      bucket.definitions.add(e.data.definition);
    }
    if (e.data?.text_evidence) {
      evidence.add(e.data.text_evidence);
      bucket.evidence.add(e.data.text_evidence);
    }
  }

  const byDocument = Array.from(perDoc.entries())
    .map(([documentId, v]) => ({
      documentId,
      documentLabel: nodeLabelById.get(documentId) ?? documentId,
      definitions: Array.from(v.definitions),
      evidence: Array.from(v.evidence),
    }))
    .sort((a, b) => a.documentLabel.localeCompare(b.documentLabel));

  return {
    definitions: Array.from(definitions),
    evidence: Array.from(evidence),
    byDocument,
  };
}

export function GraphViewer({ graph, onExpand }: Props) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [layoutMode, setLayoutMode] = useState<LayoutMode>('compact');
  const [filterKinds, setFilterKinds] = useState<Record<GraphNodeKind, boolean>>({
    class: true,
    document: true,
    concept: true,
  });
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);

  const selectedNode = useMemo(
    () => graph.nodes.find((n) => n.id === selectedId) ?? null,
    [graph.nodes, selectedId]
  );

  const filteredGraph = useMemo(() => {
    const allowedNodeIds = new Set(
      graph.nodes.filter((n) => filterKinds[n.kind]).map((n) => n.id)
    );
    return {
      nodes: graph.nodes.filter((n) => allowedNodeIds.has(n.id)),
      edges: graph.edges.filter((e) => allowedNodeIds.has(e.source) && allowedNodeIds.has(e.target)),
    };
  }, [graph, filterKinds]);

  const { rfNodes, rfEdges } = useMemo(
    () => toReactFlow(filteredGraph, layoutMode),
    [filteredGraph, layoutMode]
  );

  useEffect(() => {
    // When layout changes, re-fit so you don't have to hunt for nodes.
    rfInstance?.fitView({ padding: 0.2, duration: 250 });
  }, [layoutMode, rfInstance, rfNodes.length, rfEdges.length]);

  const onNodeClick: NodeMouseHandler = (_evt, node) => {
    setSelectedId(String(node.id));
  };

  const selectedSummary = selectedNode ? summarizeNode(selectedNode, graph) : null;

  return (
    <div className="flex h-[calc(100vh-10rem)] min-h-[520px] w-full gap-4">
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm text-muted-foreground">Show:</span>
          {(['class', 'document', 'concept'] as const).map((k) => (
            <Button
              key={k}
              type="button"
              variant={filterKinds[k] ? 'default' : 'secondary'}
              size="sm"
              onClick={() => setFilterKinds((prev) => ({ ...prev, [k]: !prev[k] }))}
            >
              {k}
            </Button>
          ))}
          <span className="ml-2 text-sm text-muted-foreground">Layout:</span>
          {(['compact', 'scatter'] as const).map((m) => (
            <Button
              key={m}
              type="button"
              variant={layoutMode === m ? 'default' : 'secondary'}
              size="sm"
              onClick={() => setLayoutMode(m)}
            >
              {m}
            </Button>
          ))}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => rfInstance?.fitView({ padding: 0.2, duration: 250 })}
          >
            Fit view
          </Button>
          {selectedNode && (
            <div className="ml-auto flex items-center gap-2">
              <Badge variant={getKindBadgeVariant(selectedNode.kind)}>{selectedNode.kind}</Badge>
              <Button type="button" size="sm" onClick={() => onExpand(selectedNode)}>
                Expand
              </Button>
            </div>
          )}
        </div>

        <div className="min-h-0 flex-1 rounded-md border">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            onNodeClick={onNodeClick}
            onInit={setRfInstance}
            fitView
          >
            <MiniMap />
            <Controls />
            <Background />
          </ReactFlow>
        </div>
      </div>

      <Sheet open={!!selectedNode} onOpenChange={(open) => !open && setSelectedId(null)}>
        <SheetContent className="w-[420px] sm:max-w-[420px]">
          <SheetHeader>
            <SheetTitle>Node details</SheetTitle>
          </SheetHeader>
          {selectedNode ? (
            <div className="space-y-4 px-4 pb-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant={getKindBadgeVariant(selectedNode.kind)}>{selectedNode.kind}</Badge>
                  <span className="font-medium">{selectedNode.label}</span>
                </div>
                <div className="text-xs text-muted-foreground">id: {selectedNode.id}</div>
              </div>

              <Separator />

              {selectedNode.kind === 'document' && (
                <div className="space-y-2 text-sm">
                  {'source_filename' in selectedNode.data && selectedNode.data.source_filename ? (
                    <div>
                      <span className="text-muted-foreground">File:</span> {selectedNode.data.source_filename}
                    </div>
                  ) : null}
                  {'topic' in selectedNode.data && selectedNode.data.topic ? (
                    <div>
                      <span className="text-muted-foreground">Topic:</span> {selectedNode.data.topic}
                    </div>
                  ) : null}
                </div>
              )}

              {selectedNode.kind === 'concept' && selectedSummary ? (
                <div className="space-y-3">
                  <div className="text-sm text-muted-foreground">
                    Mentioned in {selectedSummary.byDocument.length} document(s)
                  </div>

                  {selectedSummary.definitions.length > 0 ? (
                    <div className="space-y-1">
                      <div className="text-sm font-medium">All definitions</div>
                      <ul className="list-disc space-y-1 pl-5 text-sm">
                        {selectedSummary.definitions.slice(0, 5).map((d) => (
                          <li key={d} className="text-muted-foreground">
                            {d}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground">No definitions captured yet.</div>
                  )}

                  {selectedSummary.evidence.length > 0 ? (
                    <div className="space-y-1">
                      <div className="text-sm font-medium">All evidence</div>
                      <ul className="list-disc space-y-1 pl-5 text-sm">
                        {selectedSummary.evidence.slice(0, 3).map((ev) => (
                          <li key={ev} className="text-muted-foreground">
                            {ev}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {selectedSummary.byDocument.length > 0 ? (
                    <div className="space-y-2">
                      <div className="text-sm font-medium">By document</div>
                      <div className="space-y-3">
                        {selectedSummary.byDocument.slice(0, 10).map((d) => (
                          <div key={d.documentId} className="rounded-md border p-3">
                            <div className="text-sm font-medium">{d.documentLabel}</div>
                            {d.definitions.length > 0 ? (
                              <div className="mt-2">
                                <div className="text-xs text-muted-foreground">Definitions</div>
                                <ul className="list-disc space-y-1 pl-5 text-sm">
                                  {d.definitions.slice(0, 2).map((def) => (
                                    <li key={def} className="text-muted-foreground">
                                      {def}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                            {d.evidence.length > 0 ? (
                              <div className="mt-2">
                                <div className="text-xs text-muted-foreground">Evidence</div>
                                <ul className="list-disc space-y-1 pl-5 text-sm">
                                  {d.evidence.slice(0, 2).map((ev) => (
                                    <li key={ev} className="text-muted-foreground">
                                      {ev}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        ))}
                      </div>
                      {selectedSummary.byDocument.length > 10 ? (
                        <div className="text-xs text-muted-foreground">
                          Showing first 10 documents. Use Expand to load more, then reopen this panel.
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground">
                          Tip: if you don’t see all evidence, select the concept and click Expand to load more mentions.
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-muted-foreground">
                      No per-document evidence loaded yet. Select the concept and click Expand.
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}


