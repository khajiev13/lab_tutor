import api from '@/services/api';
import type { Course, CourseCreate, ExtractionStatus } from './types';

export const coursesApi = {
  list: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses/');
    return response.data;
  },
  listEnrolled: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses/enrolled');
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
  join: async (id: number): Promise<void> => {
    await api.post(`/courses/${id}/join`);
  },
  leave: async (id: number): Promise<void> => {
    await api.delete(`/courses/${id}/leave`);
  },
  getEnrollment: async (id: number): Promise<{ id: number } | null> => {
    const response = await api.get<{ id: number } | null>(`/courses/${id}/enrollment`);
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
