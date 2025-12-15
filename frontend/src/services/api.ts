import axios from 'axios';
import type {
  LoginCredentials,
  LoginResponse,
  RegisterData,
  UserResponse,
  Course,
  CourseCreate,
  ExtractionStatus
} from '@/types';

const API_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    // FastAPI OAuth2PasswordBearer expects form data for token endpoint
    const formData = new URLSearchParams();
    formData.append('username', credentials.email);
    formData.append('password', credentials.password);

    const response = await api.post<LoginResponse>('/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
    return response.data;
  },
  register: async (data: RegisterData): Promise<UserResponse> => {
    const response = await api.post<UserResponse>('/users/', data);
    return response.data;
  },
};

export const coursesApi = {
  list: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses/');
    return response.data;
  },
  getCourse: async (id: number): Promise<Course> => {
    const response = await api.get<Course>(`/courses/${id}`);
    return response.data;
  },
  create: async (data: CourseCreate): Promise<Course> => {
    const response = await api.post<Course>('/courses/', data);
    return response.data;
  },
  update: async (id: number, data: CourseCreate): Promise<Course> => {
    const response = await api.put<Course>(`/courses/${id}`, data);
    return response.data;
  },
  delete: async (id: number): Promise<void> => {
    await api.delete(`/courses/${id}`);
  },
  startExtraction: async (id: number): Promise<{ message: string; status: ExtractionStatus }> => {
    const response = await api.post<{ message: string; status: ExtractionStatus }>(
      `/courses/${id}/extract`
    );
    return response.data;
  },
};

export const presentationsApi = {
  list: async (courseId: number): Promise<string[]> => {
    const response = await api.get<string[]>(`/courses/${courseId}/presentations`);
    return response.data;
  },
  upload: async (courseId: number, files: File[]): Promise<void> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    await api.post(`/courses/${courseId}/presentations`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  delete: async (courseId: number, filename: string): Promise<void> => {
    await api.delete(`/courses/${courseId}/presentations/${filename}`);
  },
};

export default api;
