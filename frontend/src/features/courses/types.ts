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
  uploaded_at: string;
  status: FileProcessingStatus;
  last_error: string | null;
  processed_at: string | null;
}
