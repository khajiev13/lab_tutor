export interface CourseCreate {
  title: string;
  description?: string;
}

export type ExtractionStatus = 'not_started' | 'in_progress' | 'finished' | 'failed';

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
