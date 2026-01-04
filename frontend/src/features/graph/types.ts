export type GraphNodeKind = 'class' | 'document' | 'concept';
export type GraphEdgeKind = 'has_document' | 'mentions';

export type GraphNodeData =
  | {
      course_id: number;
      title?: string | null;
    }
  | {
      document_id: string;
      course_id: number;
      source_filename?: string | null;
      topic?: string | null;
      extracted_at?: string | null;
    }
  | {
      name: string;
    };

export interface GraphNode {
  id: string;
  kind: GraphNodeKind;
  label: string;
  data: GraphNodeData;
}

export interface GraphEdge {
  id: string;
  kind: GraphEdgeKind;
  source: string;
  target: string;
  data?: {
    definition?: string | null;
    text_evidence?: string | null;
    source_document?: string | null;
  } | null;
}

export interface CourseGraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}





