import api from '@/services/api';
import type {
  Course,
  CourseCreate,
  CourseEmbeddingStatusResponse,
  CourseFileRead,
  ExtractionStatus,
} from './types';
import type { CourseGraphResponse, GraphNodeKind } from '@/features/graph/types';
import {
  CourseFileDuplicateError,
  tryExtractContentHashFromDetail,
  tryExtractExistingFilenameFromDetail,
} from './errors';
import axios from 'axios';

export const coursesApi = {
  list: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses/');
    return response.data;
  },
  listMy: async (): Promise<Course[]> => {
    const response = await api.get<Course[]>('/courses/my');
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
  getEmbeddingsStatus: async (id: number): Promise<CourseEmbeddingStatusResponse> => {
    const response = await api.get<CourseEmbeddingStatusResponse>(`/courses/${id}/embeddings/status`);
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
  getCourseGraph: async (
    id: number,
    params?: { max_documents?: number; max_concepts?: number }
  ): Promise<CourseGraphResponse> => {
    const response = await api.get<CourseGraphResponse>(`/courses/${id}/graph`, { params });
    return response.data;
  },
  expandCourseGraph: async (
    id: number,
    params: {
      node_kind: GraphNodeKind;
      node_key?: string;
      limit?: number;
      max_concepts?: number;
    }
  ): Promise<CourseGraphResponse> => {
    const response = await api.get<CourseGraphResponse>(`/courses/${id}/graph/expand`, {
      params,
    });
    return response.data;
  },
};

export const presentationsApi = {
  list: async (courseId: number): Promise<string[]> => {
    const response = await api.get<string[]>(`/courses/${courseId}/presentations`);
    return response.data;
  },
  listStatuses: async (courseId: number): Promise<CourseFileRead[]> => {
    const response = await api.get<CourseFileRead[]>(`/courses/${courseId}/presentations/status`);
    return response.data;
  },
  upload: async (courseId: number, files: File[]): Promise<{ uploaded_files: string[] }> => {
    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });
    try {
      const response = await api.post<{ uploaded_files: string[] }>(
        `/courses/${courseId}/presentations`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.status === 409) {
        const data: unknown = error.response.data;
        const detail =
          data && typeof data === "object" && "detail" in data
            ? (data as { detail?: unknown }).detail
            : undefined;
        const existingFilename = tryExtractExistingFilenameFromDetail(detail);
        const contentHash = tryExtractContentHashFromDetail(detail);
        throw new CourseFileDuplicateError('File already uploaded', { existingFilename, contentHash });
      }
      throw error;
    }
  },
  delete: async (courseId: number, filename: string): Promise<void> => {
    await api.delete(`/courses/${courseId}/presentations/${filename}`);
  },
  deleteAll: async (courseId: number): Promise<void> => {
    await api.delete(`/courses/${courseId}/presentations`);
  },
};
