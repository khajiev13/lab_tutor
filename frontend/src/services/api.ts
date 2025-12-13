import axios from 'axios';
import type {
  LoginCredentials,
  LoginResponse,
  RegisterData,
  UserResponse,
  Course,
  CourseCreate,
  Enrollment,
} from '@/types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

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
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle token expiration
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('access_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<LoginResponse> => {
    const response = await api.post<LoginResponse>('/auth/login', credentials);
    return response.data;
  },

  register: async (data: RegisterData): Promise<UserResponse> => {
    const response = await api.post<UserResponse>('/auth/register', data);
    return response.data;
  },
};

export const coursesApi = {
  list: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses');
    return response.data;
  },

  create: async (data: CourseCreate): Promise<Course> => {
    const response = await api.post<Course>('/courses', data);
    return response.data;
  },

  update: async (id: number, data: CourseCreate): Promise<Course> => {
    const response = await api.put<Course>(`/courses/${id}`, data);
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/courses/${id}`);
  },

  join: async (id: number): Promise<Enrollment> => {
    const response = await api.post<Enrollment>(`/courses/${id}/join`);
    return response.data;
  },

  uploadPresentations: async (id: number, files: File[]): Promise<{ uploaded_files: string[] }> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    
    const response = await api.post<{ uploaded_files: string[] }>(
      `/courses/${id}/presentations`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    );
    return response.data;
  },
};

export const presentationsApi = {
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

  list: async (courseId: number): Promise<string[]> => {
    const response = await api.get<string[]>(`/courses/${courseId}/presentations`);
    return response.data;
  },

  delete: async (courseId: number, filename: string): Promise<void> => {
    await api.delete(`/courses/${courseId}/presentations/${filename}`);
  },

  deleteAll: async (courseId: number): Promise<void> => {
    await api.delete(`/courses/${courseId}/presentations`);
  },
};

export default api;
