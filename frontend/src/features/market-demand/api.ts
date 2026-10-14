import type {
  AgentState,
  ChatMessage,
  StreamEvent,
  SourceConfiguration,
  JobSourceAvailability,
  OnetRelease,
  OnetOccupation,
  SkillReview,
  SkillReviewDraft,
  SkillReviewRevision,
  SkillSelectionConfirmation,
  IntegrationApproval,
  IntegrationApprovalResponse,
  PostingEvidence,
  WorkspaceContext,
  ExecutionStatus,
  OccupationSkills,
} from "@/features/market-demand/types";
import api from "@/services/api";
import { isAxiosError } from "axios";

const DEFAULT_PROD_API_URL = "";
const DEV_HOST = typeof window !== "undefined" ? window.location.hostname : "localhost";
const DEFAULT_DEV_API_URL = `http://${DEV_HOST}:8000`;
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : DEFAULT_DEV_API_URL);

function getAccessToken(): string | null {
  return localStorage.getItem("access_token");
}

interface StreamCallbacks {
  courseId: number;
  message: string;
  onEvent: (event: StreamEvent) => void;
  onThreadId?: (threadId: string) => void;
  onError?: (err: unknown) => void;
  signal?: AbortSignal;
}
export type StreamChatArgs = StreamCallbacks & (
  | ({mode: "workflow"; country: string | null; workspace_context?: never} & Partial<SourceConfiguration>)
  | ({mode: "contextual"; workspace_context: WorkspaceContext; country?: never} & {[K in keyof SourceConfiguration]?: never})
);

export class MarketDemandApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly recovery: string;
  constructor(status: number, code: string, message: string, recovery: string) {
    super(message);
    this.name = "MarketDemandApiError";
    this.status = status;
    this.code = code;
    this.recovery = recovery;
  }
}

function responseError(status: number, data: unknown): MarketDemandApiError {
  const detail = typeof data === "object" && data !== null && "detail" in data ? data.detail : data;
  const structured = typeof detail === "object" && detail !== null ? detail as Record<string, unknown> : {};
  return new MarketDemandApiError(
    status,
    typeof structured.code === "string" ? structured.code : "request_failed",
    typeof structured.message === "string" ? structured.message : typeof detail === "string" ? detail : `Market demand request failed (${status})`,
    typeof structured.recovery === "string" ? structured.recovery : "Refresh execution status, conversation and review before retrying.",
  );
}

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return null;
  try {
    const { authApi } = await import("@/features/auth/api");
    const tokens = await authApi.refresh(refreshToken);
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    return tokens.access_token;
  } catch {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    return null;
  }
}

async function fetchWithAuth(
  url: string,
  body: string,
  token: string,
  signal?: AbortSignal,
): Promise<Response> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body,
    signal,
  });

  if (res.status === 401) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return fetch(url, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${newToken}`,
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body,
        signal,
      });
    }
  }

  return res;
}

export async function streamMarketDemandChat(args: StreamChatArgs): Promise<void> {
  if (args.mode !== "workflow" && args.mode !== "contextual") throw new Error("Choose an explicit conversation mode");
  if (args.mode === "contextual" && !args.workspace_context) throw new Error("Workspace context is required for a contextual question");
  const {courseId, message, onEvent, onThreadId, onError, signal} = args;
  const token = getAccessToken();
  if (!token) {
    throw new Error("Not authenticated");
  }

  const url = `${API_URL}/courses/${courseId}/market-demand/chat`;
  const body = JSON.stringify(args.mode === "contextual" ? {
    message, workspace_context: args.workspace_context,
  } : {
    message,
    ...(args.country ? {country: args.country} : {}),
    ...(args.sources !== undefined ? {sources: args.sources} : {}),
    ...(args.evidence_sources !== undefined ? {evidence_sources: args.evidence_sources} : {}),
    ...(args.onet_release !== undefined ? {onet_release: args.onet_release} : {}),
    ...(args.onet_occupation_codes !== undefined ? {onet_occupation_codes: args.onet_occupation_codes} : {}),
  });
  const res = await fetchWithAuth(url, body, token, signal);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    let data: unknown = text;
    try {data = JSON.parse(text);} catch { /* Plain legacy HTTP detail. */ }
    throw responseError(res.status, data);
  }

  // Capture thread_id from response header
  const returnedThreadId = res.headers.get("X-Thread-Id");
  if (returnedThreadId && onThreadId) {
    onThreadId(returnedThreadId);
  }

  if (!res.body) {
    throw new Error("Streaming not supported by the browser");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) throw new DOMException("Response detached", "AbortError");
      const {value, done} = await reader.read();
      buffer += decoder.decode(value, {stream: !done});
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        let eventType: string | undefined;
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) eventType = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        if (!data.length) continue;
        const parsed = JSON.parse(data.join("\n"));
        if (!parsed || typeof parsed !== "object") throw new Error("Invalid stream frame");
        if (!parsed.type && eventType) parsed.type = eventType;
        onEvent(parsed as StreamEvent);
      }
      if (done) {
        if (buffer.split(/\r?\n/).some(line => line.trim() && !line.startsWith(":"))) throw new Error("Response ended with an incomplete stream frame");
        break;
      }
    }
  } catch (cause) {
    onError?.(cause);
    throw cause;
  } finally {
    reader.releaseLock();
  }
}

export interface HistoryResponse {
  messages: ChatMessage[];
  threadId: string;
  outcome?: "unknown";
}

export async function fetchConversationHistory(courseId: number, signal?: AbortSignal): Promise<HistoryResponse> {
  const { data } = await api.get<HistoryResponse>(
    `/courses/${courseId}/market-demand/history`, {signal},
  );
  return data;
}

export async function fetchAgentState(courseId: number, signal?: AbortSignal): Promise<AgentState> {
  const { data } = await api.get<AgentState>(
    `/courses/${courseId}/market-demand/state`, {signal},
  );
  return data;
}

export async function deleteConversation(courseId: number): Promise<void> {
  try {
    await api.delete(`/courses/${courseId}/market-demand/history`);
  } catch (cause) {
    if (isAxiosError(cause) && cause.response) throw responseError(cause.response.status, cause.response.data);
    throw cause;
  }
}

export async function fetchJobSources(
  courseId: number,
  country: string,
  signal?: AbortSignal,
): Promise<JobSourceAvailability[]> {
  const { data } = await api.get<JobSourceAvailability[]>(
    `/courses/${courseId}/market-demand/sources`,
    { params: { country }, signal },
  );
  return data;
}

export async function fetchOnetReleases(
  courseId: number,
  signal?: AbortSignal,
): Promise<{ items: OnetRelease[] }> {
  const { data } = await api.get<{ items: OnetRelease[] }>(
    `/courses/${courseId}/occupation-reference/releases`,
    { signal },
  );
  return data;
}

export async function searchOnetOccupations(
  courseId: number,
  release: string,
  q: string,
  offset = 0,
  limit = 20,
  signal?: AbortSignal,
): Promise<{ items: OnetOccupation[]; total: number; release: string }> {
  const { data } = await api.get<{ items: OnetOccupation[]; total: number; release: string }>(
    `/courses/${courseId}/occupation-reference/occupations`,
    { params: { release, q, offset, limit }, signal },
  );
  return data;
}

export async function getOccupationSkills(
  courseId: number,
  release: string,
  socCode: string,
  signal?: AbortSignal,
): Promise<OccupationSkills> {
  const {data} = await api.get<OccupationSkills>(
    `/courses/${courseId}/occupation-reference/occupations/${encodeURIComponent(socCode)}/skills`,
    {params: {release}, signal},
  );
  return data;
}

export async function confirmOnetOccupations(
  courseId: number,
  body: { run_id: string; expected_candidate_revision: number; release: string; soc_codes: string[] },
): Promise<SkillReview> {
  const { data } = await api.post<SkillReview>(
    `/courses/${courseId}/market-demand/occupations`,
    body,
  );
  return data;
}

export async function fetchSkillReview(courseId: number, signal?: AbortSignal): Promise<SkillReview> {
  const { data } = await api.get<SkillReview>(
    `/courses/${courseId}/market-demand/skill-review`,
    { signal },
  );
  return data;
}

export async function saveSkillReviewDraft(courseId: number, body: SkillReviewDraft): Promise<SkillReview> {
  const { data } = await api.put<SkillReview>(
    `/courses/${courseId}/market-demand/skill-review/draft`,
    body,
  );
  return data;
}

export async function confirmSkillReviewSelection(courseId: number, body: SkillReviewRevision | SkillSelectionConfirmation): Promise<SkillReview> {
  const { data } = await api.post<SkillReview>(
    `/courses/${courseId}/market-demand/skill-review/selection-confirmation`, body,
  );
  return data;
}

export async function continueWithAvailableEvidence(courseId: number, body: SkillReviewRevision): Promise<SkillReview> {
  const { data } = await api.post<SkillReview>(
    `/courses/${courseId}/market-demand/skill-review/continue-with-available-evidence`, body,
  );
  return data;
}

export async function prepareSkillWithdrawal(courseId: number, body: SkillReviewRevision): Promise<SkillReview> {
  const { data } = await api.post<SkillReview>(
    `/courses/${courseId}/market-demand/skill-review/withdrawal-review`, body,
  );
  return data;
}

export async function approveSkillIntegration(courseId: number, body: IntegrationApproval): Promise<IntegrationApprovalResponse> {
  const { data } = await api.post<IntegrationApprovalResponse>(
    `/courses/${courseId}/market-demand/integration-approval`, body,
  );
  return data;
}

export async function fetchPostingEvidence(courseId: number, snapshotId: string, signal?: AbortSignal): Promise<PostingEvidence> {
  const { data } = await api.get<PostingEvidence>(
    `/courses/${courseId}/market-demand/skill-review/postings/${encodeURIComponent(snapshotId)}`, { signal },
  );
  return data;
}

export function skillReviewErrorMessage(cause: unknown, fallback: string): string {
  if (isAxiosError(cause)) {
    const detail = cause.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail.message === "string") return detail.message;
    if (detail) return fallback;
  }
  return cause instanceof Error ? cause.message : fallback;
}

export async function getMarketExecutionStatus(courseId: number, signal?: AbortSignal): Promise<ExecutionStatus> {
  const {data} = await api.get<ExecutionStatus>(`/courses/${courseId}/market-demand/execution-status`, {signal});
  return data;
}
