export interface CourseCreate {
  title: string;
  description?: string;
}

export type ExtractionStatus = 'not_started' | 'in_progress' | 'finished' | 'failed';

export type FileProcessingStatus = 'pending' | 'processing' | 'processed' | 'failed';

export interface Course extends CourseCreate {
  id: number;
  teacher_id: number;
  created_at: string;
  extraction_status: ExtractionStatus;
}

export interface Enrollment {
  id: number;
  course_id: number;
  student_id: number;
  created_at: string;
}

export interface CourseFileRead {
  id: number;
  course_id: number;
  filename: string;
  blob_path: string;
  content_hash: string | null;
  uploaded_at: string;
  status: FileProcessingStatus;
  last_error: string | null;
  processed_at: string | null;
}

export type EmbeddingStatus = 'not_started' | 'in_progress' | 'completed' | 'failed';

export interface CourseFileEmbeddingStatus {
  id: number;
  filename: string;
  status: FileProcessingStatus;
  content_hash: string | null;
  processed_at: string | null;
  last_error: string | null;

  document_id: string | null;
  embedding_status: EmbeddingStatus;
  embedded_at: string | null;
  embedding_last_error: string | null;
}

export interface CourseEmbeddingStatusResponse {
  course_id: number;
  extraction_status: ExtractionStatus;
  embedding_status: EmbeddingStatus;
  embedding_started_at: string | null;
  embedding_finished_at: string | null;
  embedding_last_error: string | null;
  files: CourseFileEmbeddingStatus[];
}
