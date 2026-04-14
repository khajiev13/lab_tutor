import api from '@/services/api';

export async function listCourseConcepts(courseId: number): Promise<string[]> {
  const res = await api.get<string[]>('/normalization/concepts', {
    params: { course_id: courseId },
  });
  return res.data;
}

export type MergeProposalDecision = 'pending' | 'approved' | 'rejected';

export type MergeProposal = {
  id: string;
  concept_a: string;
  concept_b: string;
  canonical: string;
  variants: string[];
  r: string;
  decision: MergeProposalDecision;
  comment: string;
  applied: boolean;
};

export type NormalizationReview = {
  id: string;
  course_id: number;
  status: 'pending' | 'applied';
  created_by_user_id: number | null;
  created_at: string | null;
  proposals: MergeProposal[];
  definitions: Record<string, string[]>;
};

export type MergeDecisionUpdate = {
  proposal_id: string;
  decision: MergeProposalDecision;
  comment?: string | null;
};

export type UpdateMergeDecisionsResponse = {
  review_id: string;
  updated: number;
};

export type ApplyReviewResponse = {
  review_id: string;
  total_approved: number;
  applied: number;
  skipped: number;
  failed: number;
  errors: string[];
};

export async function getNormalizationReview(
  courseId: number,
  reviewId: string
): Promise<NormalizationReview> {
  const res = await api.get<NormalizationReview>(`/normalization/reviews/${reviewId}`, {
    params: { course_id: courseId },
  });
  return res.data;
}

export async function updateNormalizationReviewDecisions(
  courseId: number,
  reviewId: string,
  decisions: MergeDecisionUpdate[]
): Promise<UpdateMergeDecisionsResponse> {
  const res = await api.post<UpdateMergeDecisionsResponse>(
    `/normalization/reviews/${reviewId}/decisions`,
    { decisions },
    { params: { course_id: courseId } }
  );
  return res.data;
}

export async function applyNormalizationReview(
  courseId: number,
  reviewId: string
): Promise<ApplyReviewResponse> {
  const res = await api.post<ApplyReviewResponse>(
    `/normalization/reviews/${reviewId}/apply`,
    {},
    { params: { course_id: courseId } }
  );
  return res.data;
}
