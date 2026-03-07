import api from '@/services/api';
import type {
  BookAnalysisSummary,
  BookCandidate,
  BookExtractionRun,
  BookSelectionSession,
  ChapterAnalysisSummary,
  CourseSelectedBook,
  ExtractionPreviewResponse,
  ManualUploadResponse,
  SelectBooksRequest,
  SelectedBookManualUploadResponse,
  StartSessionRequest,
} from './types';

// ── REST endpoints ─────────────────────────────────────────────

export async function createSession(
  courseId: number,
  body: StartSessionRequest,
): Promise<BookSelectionSession> {
  const res = await api.post<BookSelectionSession>(
    '/book-selection/sessions',
    body,
    { params: { course_id: courseId } },
  );
  return res.data;
}

export async function getSession(sessionId: number): Promise<BookSelectionSession> {
  const res = await api.get<BookSelectionSession>(
    `/book-selection/sessions/${sessionId}`,
  );
  return res.data;
}

export async function getLatestSession(
  courseId: number,
): Promise<BookSelectionSession | null> {
  const res = await api.get<BookSelectionSession | null>(
    `/book-selection/courses/${courseId}/session`,
  );
  return res.data;
}

export async function getSessionBooks(
  sessionId: number,
): Promise<BookCandidate[]> {
  const res = await api.get<BookCandidate[]>(
    `/book-selection/sessions/${sessionId}/books`,
  );
  return res.data;
}

export async function getCourseBooks(
  courseId: number,
): Promise<BookCandidate[]> {
  const res = await api.get<BookCandidate[]>(
    `/book-selection/courses/${courseId}/books`,
  );
  return res.data;
}

export async function uploadBookManually(
  sessionId: number,
  bookId: number,
  file: File,
): Promise<ManualUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await api.post<ManualUploadResponse>(
    `/book-selection/sessions/${sessionId}/books/${bookId}/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

export async function uploadCustomBook(
  courseId: number,
  file: File,
  title: string,
  authors?: string,
): Promise<BookCandidate> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title);
  if (authors) form.append('authors', authors);
  const res = await api.post<BookCandidate>(
    `/book-selection/courses/${courseId}/books/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

// ── Course Selected Books endpoints ────────────────────────────

export async function getCourseSelectedBooks(
  courseId: number,
): Promise<CourseSelectedBook[]> {
  const res = await api.get<CourseSelectedBook[]>(
    `/book-selection/courses/${courseId}/selected-books`,
  );
  return res.data;
}

export async function uploadToSelectedBook(
  selectedBookId: number,
  file: File,
): Promise<SelectedBookManualUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await api.post<SelectedBookManualUploadResponse>(
    `/book-selection/selected-books/${selectedBookId}/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

export async function ignoreSelectedBook(
  selectedBookId: number,
): Promise<CourseSelectedBook> {
  const res = await api.patch<CourseSelectedBook>(
    `/book-selection/selected-books/${selectedBookId}/ignore`,
  );
  return res.data;
}

export async function uploadCustomSelectedBook(
  courseId: number,
  file: File,
  title: string,
  authors?: string,
): Promise<CourseSelectedBook> {
  const form = new FormData();
  form.append('file', file);
  form.append('title', title);
  if (authors) form.append('authors', authors);
  const res = await api.post<CourseSelectedBook>(
    `/book-selection/courses/${courseId}/selected-books/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  );
  return res.data;
}

// ── Background task endpoints (replace SSE) ────────────────────

/** Kick off discovery + scoring in the background. Returns immediately. */
export async function runDiscovery(
  sessionId: number,
): Promise<BookSelectionSession> {
  const res = await api.post<BookSelectionSession>(
    `/book-selection/sessions/${sessionId}/run`,
  );
  return res.data;
}

/** Resume a failed/interrupted scoring session. Returns immediately. */
export async function resumeScoring(
  sessionId: number,
): Promise<BookSelectionSession> {
  const res = await api.post<BookSelectionSession>(
    `/book-selection/sessions/${sessionId}/resume`,
  );
  return res.data;
}

/** Re-run discovery from scratch (clears previous results). Returns immediately. */
export async function rediscoverBooks(
  sessionId: number,
): Promise<BookSelectionSession> {
  const res = await api.post<BookSelectionSession>(
    `/book-selection/sessions/${sessionId}/rediscover`,
  );
  return res.data;
}

/** Delete all selected books and reset session to awaiting_review. */
export async function reselectBooks(
  sessionId: number,
): Promise<BookSelectionSession> {
  const res = await api.post<BookSelectionSession>(
    `/book-selection/sessions/${sessionId}/reselect`,
  );
  return res.data;
}

/** Select books and start downloads in the background. Returns immediately. */
export async function selectAndDownload(
  sessionId: number,
  bookIds: number[],
): Promise<void> {
  await api.post(
    `/book-selection/sessions/${sessionId}/select`,
    { book_ids: bookIds } satisfies SelectBooksRequest,
  );
}

// ── Book Analysis endpoints ────────────────────────────────────

/** Trigger a new analysis run (dual strategy). Returns 202.
 *  Throws with status 409 if a run is already in progress.
 */
export async function triggerAnalysis(
  courseId: number,
  signal?: AbortSignal,
): Promise<BookExtractionRun> {
  const res = await api.post<BookExtractionRun>(
    `/book-selection/courses/${courseId}/analysis`,
    undefined,
    { signal },
  );
  return res.data;
}

/** Get the latest analysis run for a course (or null). */
export async function getLatestAnalysis(
  courseId: number,
): Promise<BookExtractionRun | null> {
  const res = await api.get<BookExtractionRun | null>(
    `/book-selection/courses/${courseId}/analysis/latest`,
  );
  return res.data;
}

/** Pick a book from the analysis results. */
export async function pickBook(
  runId: number,
  courseId: number,
  selectedBookId: number,
): Promise<BookExtractionRun> {
  const res = await api.post<BookExtractionRun>(
    `/book-selection/courses/${courseId}/analysis/${runId}/pick/${selectedBookId}`,
  );
  return res.data;
}

/** Get scored summaries for a specific analysis run. */
export async function getAnalysisSummaries(
  courseId: number,
  runId: number,
): Promise<BookAnalysisSummary[]> {
  const res = await api.get<BookAnalysisSummary[]>(
    `/book-selection/courses/${courseId}/analysis/${runId}/summaries`,
  );
  return res.data;
}

// ── Chapter-level analysis endpoints ───────────────────────────

/** Trigger chapter-level concept scoring for all books in a run. */
export async function triggerChapterScoring(
  courseId: number,
  runId: number,
): Promise<ChapterAnalysisSummary[]> {
  const res = await api.post<ChapterAnalysisSummary[]>(
    `/book-selection/courses/${courseId}/analysis/${runId}/chapter-scoring`,
  );
  return res.data;
}

/** Get pre-computed chapter-level analysis summaries for a run. */
export async function getChapterSummaries(
  courseId: number,
  runId: number,
): Promise<ChapterAnalysisSummary[]> {
  const res = await api.get<ChapterAnalysisSummary[]>(
    `/book-selection/courses/${courseId}/analysis/${runId}/chapter-summaries`,
  );
  return res.data;
}

/**
 * Open an SSE stream for agentic chapter-level extraction.
 * Uses named SSE events (event: + data:) — the JSON payload includes a `type` field.
 * Returns an AbortController so the caller can tear down the stream.
 */
export function openAgenticExtractionStream(
  courseId: number,
  runId: number,
  onEvent: (evt: import('./types').AgenticStreamEvent) => void,
  onDone?: () => void,
  onError?: (err: unknown) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    const baseUrl = (api.defaults.baseURL ?? '').replace(/\/$/, '');
    const url = `${baseUrl}/book-selection/courses/${courseId}/analysis/${runId}/agentic`;

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(url, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => 'Unknown error');
        onError?.(new Error(`SSE request failed (${res.status}): ${text}`));
        onDone?.();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          let data: string | null = null;
          for (const line of raw.split('\n')) {
            if (line.startsWith('data:')) {
              data = line.slice(5).trim();
            }
          }
          if (data) {
            try {
              onEvent(JSON.parse(data) as import('./types').AgenticStreamEvent);
            } catch {
              // malformed frame
            }
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) onError?.(err);
    }
    onDone?.();
  })();

  return controller;
}

/**
 * Open an SSE stream for per-book chunk-embedding progress.
 * Returns an AbortController so the caller can tear down the stream.
 *
 * Automatically retries on failure (up to 10 times with 3 s back-off)
 * unless the caller aborts via the returned controller.
 */
export function openEmbeddingProgressStream(
  courseId: number,
  runId: number,
  onData: (data: import('./types').EmbeddingProgressEvent) => void,
  onDone?: () => void,
): AbortController {
  const controller = new AbortController();
  const MAX_RETRIES = 10;
  const RETRY_MS = 3_000;

  (async () => {
    const baseUrl = (api.defaults.baseURL ?? '').replace(/\/$/, '');
    const url = `${baseUrl}/book-selection/courses/${courseId}/analysis/${runId}/embedding-progress`;

    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
      if (controller.signal.aborted) break;

      try {
        const token = localStorage.getItem('access_token');
        const res = await fetch(url, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: controller.signal,
        });
        if (!res.ok || !res.body) {
          // Server returned an error — retry after delay
          await new Promise((r) => setTimeout(r, RETRY_MS));
          continue;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() ?? '';
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                onData(
                  JSON.parse(line.slice(6)) as import('./types').EmbeddingProgressEvent,
                );
              } catch {
                // ignore malformed SSE frames
              }
            }
          }
        }
        // Stream ended normally (server closed it) — no retry needed
        break;
      } catch {
        if (controller.signal.aborted) break;
        // Network error — retry after delay
        await new Promise((r) => setTimeout(r, RETRY_MS));
      }
    }
    onDone?.();
  })();

  return controller;
}

/**
 * Open an SSE stream for content recommendations.
 * Returns an AbortController so the caller can tear down the stream.
 */
export function openRecommendationStream(
  courseId: number,
  runId: number,
  selectedBookId: number,
  onEvent: (evt: import('./types').RecommendationStreamEvent) => void,
  onDone?: () => void,
  onError?: (err: unknown) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    const baseUrl = (api.defaults.baseURL ?? '').replace(/\/$/, '');
    const url = `${baseUrl}/book-selection/courses/${courseId}/analysis/${runId}/books/${selectedBookId}/recommendations`;

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(url, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => 'Unknown error');
        onError?.(new Error(`SSE request failed (${res.status}): ${text}`));
        onDone?.();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          let data: string | null = null;
          for (const line of raw.split('\n')) {
            if (line.startsWith('data:')) {
              data = line.slice(5).trim();
            }
          }
          if (data) {
            try {
              onEvent(JSON.parse(data) as import('./types').RecommendationStreamEvent);
            } catch {
              // malformed frame
            }
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) onError?.(err);
    }
    onDone?.();
  })();

  return controller;
}

/**
 * Open an SSE stream for curriculum graph construction.
 * Returns an AbortController so the caller can tear down the stream.
 */
export function openCurriculumBuildStream(
  courseId: number,
  runId: number,
  selectedBookId: number,
  onEvent: (evt: import('./types').CurriculumBuildEvent) => void,
  onDone?: () => void,
  onError?: (err: unknown) => void,
): AbortController {
  const controller = new AbortController();

  (async () => {
    const baseUrl = (api.defaults.baseURL ?? '').replace(/\/$/, '');
    const url = `${baseUrl}/book-selection/courses/${courseId}/analysis/${runId}/build-curriculum/${selectedBookId}`;

    try {
      const token = localStorage.getItem('access_token');
      const res = await fetch(url, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => 'Unknown error');
        onError?.(new Error(`SSE request failed (${res.status}): ${text}`));
        onDone?.();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx: number;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);

          let data: string | null = null;
          for (const line of raw.split('\n')) {
            if (line.startsWith('data:')) {
              data = line.slice(5).trim();
            }
          }
          if (data) {
            try {
              onEvent(JSON.parse(data) as import('./types').CurriculumBuildEvent);
            } catch {
              // malformed frame
            }
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) onError?.(err);
    }
    onDone?.();
  })();

  return controller;
}

// ── Extraction Inspector endpoints ─────────────────────────────

/** Trigger extraction-only (stops at chapter_extracted for review). */
export async function triggerExtractionOnly(
  courseId: number,
): Promise<BookExtractionRun> {
  const res = await api.post<BookExtractionRun>(
    `/book-selection/courses/${courseId}/analysis/extract-only`,
  );
  return res.data;
}

/** Get extracted chapters/sections preview for human inspection. */
export async function getExtractionPreview(
  courseId: number,
  runId: number,
): Promise<ExtractionPreviewResponse> {
  const res = await api.get<ExtractionPreviewResponse>(
    `/book-selection/courses/${courseId}/analysis/${runId}/extraction-preview`,
  );
  return res.data;
}

/** Approve extraction and continue to chunking pipeline. */
export async function approveExtraction(
  courseId: number,
  runId: number,
): Promise<BookExtractionRun> {
  const res = await api.post<BookExtractionRun>(
    `/book-selection/courses/${courseId}/analysis/${runId}/approve-extraction`,
  );
  return res.data;
}
