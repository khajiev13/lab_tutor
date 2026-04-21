import api from '@/services/api';
import type {
  Course,
  CourseCreate,
  CourseEmbeddingStatusResponse,
  CourseFileRead,
  ExtractionStatus,
} from './types';
import type {
  SkillBanksResponse,
  StudentInsightsOverview,
  TeacherStudentInsightDetail,
} from '@/features/curriculum/types';
import {
  CourseFileDuplicateError,
  tryExtractContentHashFromDetail,
  tryExtractExistingFilenameFromDetail,
} from './errors';
import axios from 'axios';

/* ── SSE helpers ───────────────────────────────────────────── */

const DEFAULT_PROD_API_URL = '';
const DEV_HOST = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const DEFAULT_DEV_API_URL = `http://${DEV_HOST}:8000`;
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : DEFAULT_DEV_API_URL);

function getAccessToken(): string | null {
  return localStorage.getItem('access_token');
}

export interface ExtractionProgressEvent {
  total: number;
  processed: number;
  failed: number;
  terminal: number;
  value: number;
  files: { filename: string; status: string; last_error: string | null }[];
}

export interface ExtractionCompleteEvent extends ExtractionProgressEvent {
  status: ExtractionStatus;
}

interface StreamExtractionArgs {
  courseId: number;
  onProgress: (event: ExtractionProgressEvent) => void;
  onComplete: (event: ExtractionCompleteEvent) => void;
  onError?: (err: unknown) => void;
  signal?: AbortSignal;
}

export async function streamExtraction({
  courseId,
  onProgress,
  onComplete,
  onError,
  signal,
}: StreamExtractionArgs): Promise<void> {
  const token = getAccessToken();
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(`${API_URL}/courses/${courseId}/extract/stream`, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `Extraction stream failed (${res.status})`);
  }

  if (!res.body) throw new Error('Streaming not supported by the browser');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const rawMessage = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        // Skip SSE comments (keep-alive)
        if (rawMessage.startsWith(':')) continue;

        const lines = rawMessage.split('\n').map((l) => l.trimEnd());
        let eventType: string | null = null;
        let eventData: string | null = null;

        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith('event:')) {
            eventType = line.slice('event:'.length).trim();
          } else if (line.startsWith('data:')) {
            eventData = line.slice('data:'.length).trim();
          }
        }

        if (!eventData) continue;

        try {
          const parsed = JSON.parse(eventData);
          if (eventType === 'complete') {
            onComplete(parsed as ExtractionCompleteEvent);
          } else if (eventType === 'progress') {
            onProgress(parsed as ExtractionProgressEvent);
          } else if (eventType === 'error') {
            onError?.(new Error(parsed.error || 'Unknown SSE error'));
          }
        } catch (e) {
          onError?.(e);
        }
      }
    }
  } catch (e) {
    const isAbort =
      typeof e === 'object' &&
      e !== null &&
      'name' in e &&
      (e as { name: string }).name === 'AbortError';
    if (!isAbort) onError?.(e);
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}

/* ── REST API ──────────────────────────────────────────────── */

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
  getSkillBanks: async (id: number): Promise<SkillBanksResponse> => {
    const response = await api.get<SkillBanksResponse>(`/courses/${id}/skill-banks`);
    return response.data;
  },
  getStudentInsights: async (id: number): Promise<StudentInsightsOverview> => {
    const response = await api.get<StudentInsightsOverview>(`/courses/${id}/student-insights`);
    return response.data;
  },
  getStudentInsightDetail: async (
    courseId: number,
    studentId: number,
  ): Promise<TeacherStudentInsightDetail> => {
    const response = await api.get<TeacherStudentInsightDetail>(
      `/courses/${courseId}/student-insights/${studentId}`,
    );
    return response.data;
  },
  updateSkillSelectionRange: async (
    id: number,
    payload: { min_skills: number; max_skills: number },
  ): Promise<SkillBanksResponse['selection_range']> => {
    const response = await api.patch<SkillBanksResponse['selection_range']>(
      `/courses/${id}/skill-selection-range`,
      payload,
    );
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
