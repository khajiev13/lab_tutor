export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  role: 'student' | 'teacher';
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  role: 'student' | 'teacher';
  created_at: string;
}

export interface CourseCreate {
  title: string;
  description?: string;
}

export interface Course extends CourseCreate {
  id: number;
  teacher_id: number;
  created_at: string;
}

export interface Enrollment {
  id: number;
  course_id: number;
  student_id: number;
  created_at: string;
}
