import type { PrerequisiteDraftEdge, PrerequisiteSkill } from "@/features/courses/types";
import { buildGraphPreview } from "@/features/prerequisite-review/lib/prerequisiteGraph";

interface PrerequisiteGraphPreviewProps {
  skills: PrerequisiteSkill[];
  edges: PrerequisiteDraftEdge[];
}

export function PrerequisiteGraphPreview({ skills, edges }: PrerequisiteGraphPreviewProps) {
  const graph = buildGraphPreview(skills, edges);
  const nodeMap = new Map(graph.nodes.map((node) => [node.id, node]));

  return (
    <div className="rounded-lg border bg-background p-4">
      <h2 className="text-base font-semibold">Graph preview</h2>
      <div className="mt-4 overflow-x-auto">
        <svg
          role="img"
          aria-label="Prerequisite graph preview"
          viewBox="0 0 960 440"
          className="h-[360px] min-w-[760px] w-full"
        >
          <defs>
            <marker
              id="prerequisite-arrow"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" className="fill-foreground" />
            </marker>
          </defs>
          {graph.edges.map((edge) => {
            const source = nodeMap.get(edge.source);
            const target = nodeMap.get(edge.target);
            if (!source || !target) return null;

            return (
              <line
                key={edge.id}
                x1={source.x}
                y1={source.y}
                x2={target.x}
                y2={target.y}
                className="stroke-muted-foreground"
                strokeWidth="1.5"
                markerEnd="url(#prerequisite-arrow)"
              />
            );
          })}
          {graph.nodes.map((node) => (
            <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
              <rect
                x="-78"
                y="-22"
                width="156"
                height="44"
                rx="8"
                className="fill-background stroke-foreground"
                strokeWidth="1"
              />
              <text
                textAnchor="middle"
                dominantBaseline="middle"
                className="fill-foreground text-[12px]"
              >
                {node.label.length > 24 ? `${node.label.slice(0, 21)}...` : node.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
