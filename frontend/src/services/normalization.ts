const DEFAULT_PROD_API_URL = 'https://backend.mangoocean-d0c97d4f.westus2.azurecontainerapps.io';
const API_URL =
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? DEFAULT_PROD_API_URL : 'http://localhost:8000');

export type NormalizationPhase = 'generation' | 'validation' | 'complete';
export type NormalizationEventType = 'update' | 'complete' | 'error';

export type ConceptMerge = {
  concept_a: string;
  concept_b: string;
  canonical: string;
  variants: string[];
  r: string;
};

export type ConceptRelationship = {
  s: string;
  t: string;
  rel: string;
  r: string;
};

export type NormalizationStreamEvent = {
  type: NormalizationEventType;
  iteration: number;
  phase: NormalizationPhase;
  agent_activity: string;
  requires_review: boolean;
  review_id: string | null;
  concepts_count: number;
  merges_found: number;
  relationships_found: number;
  latest_merges: ConceptMerge[];
  latest_relationships: ConceptRelationship[];
  total_merges: number;
  total_relationships: number;
};

type StartNormalizationStreamArgs = {
  courseId: number;
  onEvent: (evt: NormalizationStreamEvent) => void;
  onError?: (err: unknown) => void;
  signal?: AbortSignal;
};

function getAccessToken(): string | null {
  return localStorage.getItem('access_token');
}

export async function startNormalizationStream({
  courseId,
  onEvent,
  onError,
  signal,
}: StartNormalizationStreamArgs): Promise<void> {
  const token = getAccessToken();
  if (!token) {
    throw new Error('Not authenticated');
  }

  const url = new URL(`${API_URL}/normalization/stream`);
  url.searchParams.set('course_id', String(courseId));

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `Normalization stream failed (${res.status})`);
  }

  if (!res.body) {
    throw new Error('Streaming not supported by the browser');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();

  let buffer = '';
  let currentEventType: string | null = null;
  let currentData: string | null = null;

  const flush = () => {
    if (!currentData) return;
    try {
      const parsed = JSON.parse(currentData) as NormalizationStreamEvent;
      onEvent(parsed);
    } catch (e) {
      onError?.(e);
    } finally {
      currentEventType = null;
      currentData = null;
    }
  };

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by a blank line.
      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const rawMessage = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        const lines = rawMessage.split('\n').map((l) => l.trimEnd());
        for (const line of lines) {
          if (!line) continue;
          if (line.startsWith('event:')) {
            currentEventType = line.slice('event:'.length).trim();
            continue;
          }
          if (line.startsWith('data:')) {
            // In our backend we send exactly one JSON line.
            currentData = line.slice('data:'.length).trim();
          }
        }

        // We ignore currentEventType for now; payload already contains `type`.
        void currentEventType;
        flush();
      }
    }
  } catch (e) {
    // Abort is not a real error for UX.
    const isAbort =
      typeof e === 'object' &&
      e !== null &&
      'name' in e &&
      typeof (e as Record<string, unknown>).name === 'string' &&
      (e as Record<string, unknown>).name === 'AbortError';
    if (!isAbort) {
      onError?.(e);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}


