export interface DocumentInfo {
  id: string;
  source_filename: string;
  topic: string | null;
  summary: string | null;
}

export interface ChapterPlan {
  number: number;
  title: string;
  description: string;
  learning_objectives: string[];
  prerequisites: string[];
  assigned_documents: string[];
}

export interface ChapterPlanResponse {
  course_id: number;
  chapters: ChapterPlan[];
  unassigned_documents: DocumentInfo[];
  all_documents: DocumentInfo[];
}

export interface SaveChapterPlanRequest {
  chapters: ChapterPlan[];
}
