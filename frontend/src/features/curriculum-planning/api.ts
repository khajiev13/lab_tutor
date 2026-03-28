import api from '@/services/api';
import type { ChapterPlanResponse, SaveChapterPlanRequest } from './types';

export async function generateChapterPlan(courseId: number): Promise<ChapterPlanResponse> {
  const res = await api.post<ChapterPlanResponse>(`/courses/${courseId}/chapter-plan/generate`);
  return res.data;
}

export async function getChapterPlan(courseId: number): Promise<ChapterPlanResponse> {
  const res = await api.get<ChapterPlanResponse>(`/courses/${courseId}/chapter-plan`);
  return res.data;
}

export async function saveChapterPlan(
  courseId: number,
  body: SaveChapterPlanRequest,
): Promise<ChapterPlanResponse> {
  const res = await api.put<ChapterPlanResponse>(`/courses/${courseId}/chapter-plan`, body);
  return res.data;
}
