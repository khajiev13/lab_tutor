/**
 * dag-layout.ts — Computes x/y positions for a layered DAG.
 *
 * Algorithm:
 *  1. Topological sort → assign each node to a "layer" (longest-path rank)
 *  2. Within each layer sort nodes by their column index
 *  3. Return (x, y) in [0..width] × [0..height] canvas space
 *
 * Usage:
 *   const { nodes, edges } = buildDagLayout(skills, atRiskIds, nextStepIds);
 */

export interface DagNode {
  id: number;
  label: string;
  layer: number;
  col: number;
  x: number;
  y: number;
  mastery: number;           // 0–1
  isAtRisk: boolean;
  isNextStep: boolean;
  nextStepRank?: number;     // 1-based rank in learning path
  domainIdx: number;
  domainColor: string;
}

export interface DagEdge {
  source: number;
  target: number;
  x1: number; y1: number;
  x2: number; y2: number;
  isOnPath: boolean;
  isCascade: boolean;  // parent has downstream decay risk
}

export interface DagLayoutResult {
  nodes: DagNode[];
  edges: DagEdge[];
  width: number;
  height: number;
}

/**
 * Build a heuristic prerequisite DAG from sub-skill structure.
 *
 * Since the A_skill matrix is not in the exported portfolio JSON, we infer
 * a simple prerequisite ordering:
 *   – Within a domain, sub-skills are ordered by their `id` (lower id → prereq of next)
 *   – Across domains, no cross-domain edges (domains are independent)
 *
 * The layout arranges domains as columns, sub-skills as rows within each column.
 */
export function buildDagLayout(
  skills: Array<{
    id: number;
    name: string;
    sub_skills: Array<{ id: number; name: string }>;
  }>,
  masteryVector: number[],
  atRiskIds: Set<number>,
  nextStepIds: Map<number, number>,   // skillId → rank (1-based)
  domainColors: string[],
  canvasWidth  = 1000,
  canvasHeight = 600,
  cascadeIds?: Set<number>,           // skill IDs where downstream decay is active
): DagLayoutResult {
  const nodes: DagNode[] = [];
  const edges: DagEdge[] = [];

  const nDomains = skills.length;
  if (nDomains === 0) return { nodes, edges, width: canvasWidth, height: canvasHeight };

  const colWidth  = canvasWidth  / nDomains;
  const nodeVGap  = 54;

  // Build node positions
  skills.forEach((domain, di) => {
    const colCenterX = colWidth * di + colWidth / 2;
    const subSkills  = domain.sub_skills;
    const nSub       = subSkills.length;
    const totalH     = nSub * nodeVGap;
    const startY     = (canvasHeight - totalH) / 2 + nodeVGap / 2;

    subSkills.forEach((ss, si) => {
      const x = colCenterX;
      const y = startY + si * nodeVGap;
      const m = masteryVector[ss.id] ?? 0;
      nodes.push({
        id:           ss.id,
        label:        ss.name,
        layer:        di,
        col:          si,
        x,
        y,
        mastery:      m,
        isAtRisk:     atRiskIds.has(ss.id),
        isNextStep:   nextStepIds.has(ss.id),
        nextStepRank: nextStepIds.get(ss.id),
        domainIdx:    di,
        domainColor:  domainColors[di % domainColors.length],
      });

      // Intra-domain prereq edge: ss[i-1] → ss[i]
      if (si > 0) {
        const prevSs = subSkills[si - 1];
        const parentHasCascade = cascadeIds ? cascadeIds.has(prevSs.id) : false;
        edges.push({
          source:    prevSs.id,
          target:    ss.id,
          x1: x,
          y1: startY + (si - 1) * nodeVGap,
          x2: x,
          y2: y,
          isOnPath:  nextStepIds.has(ss.id) || nextStepIds.has(prevSs.id),
          isCascade: parentHasCascade,
        });
      }
    });
  });

  return { nodes, edges, width: canvasWidth, height: canvasHeight };
}

/** Map mastery value (0–1) to a fill colour. */
export function masteryToColor(mastery: number): string {
  if (mastery >= 0.75) return "#10b981"; // emerald  — proficient
  if (mastery >= 0.50) return "#3b82f6"; // blue     — progressing
  if (mastery >= 0.30) return "#f59e0b"; // amber    — at-risk
  return "#ef4444";                       // red      — critical
}

/** Map mastery value to a human-readable tier label. */
export function masteryTier(mastery: number): string {
  if (mastery >= 0.75) return "Proficient";
  if (mastery >= 0.50) return "Progressing";
  if (mastery >= 0.30) return "At Risk";
  return "Critical";
}
