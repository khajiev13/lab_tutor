import api from '@/services/api';
import type {
  BookCandidate,
  BookSelectionSession,
  CourseSelectedBook,
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
