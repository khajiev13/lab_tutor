import type { PrerequisiteDraftEdge, PrerequisiteSkill } from "@/features/courses/types";

export interface PrerequisiteGraphNode {
  id: string;
  label: string;
  x: number;
  y: number;
}

export interface PrerequisiteGraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface PrerequisiteGraphPreview {
  nodes: PrerequisiteGraphNode[];
  edges: PrerequisiteGraphEdge[];
}

export function buildGraphPreview(
  skills: PrerequisiteSkill[],
  edges: PrerequisiteDraftEdge[],
): PrerequisiteGraphPreview {
  const labels = new Set<string>();

  skills.forEach((skill) => labels.add(skill.name));
  edges.forEach((edge) => {
    labels.add(edge.prerequisite_name);
    labels.add(edge.dependent_name);
  });

  const sortedLabels = [...labels].sort((a, b) => a.localeCompare(b));
  const centerX = 480;
  const centerY = 220;
  const radiusX = 340;
  const radiusY = 140;
  const singleNode = sortedLabels.length === 1;

  const nodes = sortedLabels.map((label, index) => {
    const angle = singleNode ? 0 : (index / sortedLabels.length) * Math.PI * 2 - Math.PI / 2;

    return {
      id: label,
      label,
      x: singleNode ? centerX : Math.round(centerX + Math.cos(angle) * radiusX),
      y: singleNode ? centerY : Math.round(centerY + Math.sin(angle) * radiusY),
    };
  });

  const previewEdges = edges
    .map((edge) => ({
      id: `${edge.prerequisite_name}->${edge.dependent_name}`,
      source: edge.prerequisite_name,
      target: edge.dependent_name,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  return { nodes, edges: previewEdges };
}
